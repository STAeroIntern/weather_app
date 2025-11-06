import asyncio
import aiohttp
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, send_file
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

API_KEY = "YOUR_SECRET_TOKEN"
DELAY_BETWEEN_REQUESTS = 0.2

app = Flask(__name__, template_folder='templates')

# Global cache for export
cached_df = None
cached_metadata = {}


# ---------------- Asynchronous NEA API Fetch ---------------- #
async def fetch_page(session, url, params):
    async with session.get(url, headers={"X-Api-Key": API_KEY}, params=params, timeout=10) as resp:
        resp.raise_for_status()
        return await resp.json()


async def fetch_paginated_url(session, url, dateinput):
    all_readings = []
    page_token = ""

    while True:
        params = {"date": dateinput}
        if page_token:
            params["paginationToken"] = page_token

        try:
            data = await fetch_page(session, url, params)
        except aiohttp.ClientError as e:
            print(f"Request failed for {url}: {e}")
            break

        readings = data["data"].get("readings", [])
        all_readings.extend(readings)

        page_token = data["data"].get("paginationToken")
        if not page_token:
            break

        await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

    return all_readings


async def fetch_all_urls(urls_with_dates):
    all_results = {}
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_paginated_url(session, url, dateinput) for url, dateinput in urls_with_dates]
        results = await asyncio.gather(*tasks)
        for (url, _), readings in zip(urls_with_dates, results):
            all_results[url] = readings
    return all_results


# ---------------- Routes ---------------- #

@app.route('/', methods=['GET', 'POST'])
def index():
    """Main dashboard page"""
    station_id = request.args.get('station', 'S115')
    user_date = ''
    start_time = '00:00:00'
    end_time = '23:59:59'

    if request.method == 'POST':
        user_date = request.form['user_input']
        start_time = request.form.get('start_time', '00:00:00')
        end_time = request.form.get('end_time', '23:59:59')
        station_id = request.form.get('station', station_id)

        try:
            pd.to_datetime(user_date, format='%Y-%m-%d')
        except ValueError:
            return "Invalid date format. Please use YYYY-MM-DD."

        return redirect(url_for('results', 
                                station=station_id, 
                                date=user_date, 
                                start=start_time, 
                                end=end_time))

    return render_template('template.html', station_id=station_id, user_date=user_date,
                           start_time=start_time, end_time=end_time)


@app.route('/results', methods=['GET'])
def results():
    """Fetches NEA data and displays results."""
    global cached_df, cached_metadata

    station_id = request.args.get('station', 'S115')
    user_date = request.args.get('date')
    start_time = request.args.get('start', '00:00:00')
    end_time = request.args.get('end', '23:59:59')

    if not user_date:
        return redirect(url_for('index'))

    urls_with_dates = [
        ("https://api-open.data.gov.sg/v2/real-time/api/air-temperature", user_date),
        ("https://api-open.data.gov.sg/v2/real-time/api/wind-speed", user_date),
        ("https://api-open.data.gov.sg/v2/real-time/api/rainfall", user_date),
        ("https://api-open.data.gov.sg/v2/real-time/api/relative-humidity", user_date)
    ]

    all_data = asyncio.run(fetch_all_urls(urls_with_dates))

    rows = []
    for url, readings in all_data.items():
        measure_type = "temperature" if "air-temperature" in url else \
                       "wind_speed" if "wind-speed" in url else \
                       "rainfall" if "rainfall" in url else "humidity"

        for entry in readings:
            timestamp = entry["timestamp"]
            value = next((d["value"] for d in entry["data"] if d["stationId"] == station_id), None)
            if value is not None:
                date_part, time_part = timestamp.split("T")
                time_part = time_part.split("+")[0]
                rows.append({"date": date_part, "time": time_part, measure_type: value})

    df = pd.DataFrame(rows)
    table_html = "<p>No data found for this time range.</p>"

    if not df.empty:
        df = df[(df['time'] >= start_time) & (df['time'] <= end_time)]
        df = df.pivot_table(index=["date", "time"], values=df.columns[2:], aggfunc='first').reset_index()
        table_html = df.to_html(classes="table table-bordered table-hover", index=False)

    cached_df = df
    cached_metadata = {
        "station": station_id,
        "date": user_date,
        "start": start_time,
        "end": end_time
    }

    return render_template('results.html', table_html=table_html,
                           station_id=station_id, user_date=user_date,
                           start_time=start_time, end_time=end_time)


# ---------------- Export Routes ---------------- #

@app.route('/export/<filetype>')
def export_data(filetype):
    """Exports the cached DataFrame as CSV, Excel, or PDF."""
    global cached_df, cached_metadata

    if cached_df is None or cached_df.empty:
        return "No data available to export."

    filename_base = f"NEA_{cached_metadata['station']}_{cached_metadata['date']}"

    # Export CSV
    if filetype == 'csv':
        output = BytesIO()
        cached_df.to_csv(output, index=False)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name=f"{filename_base}.csv", mimetype='text/csv')

    # Export Excel
    elif filetype == 'excel':
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            cached_df.to_excel(writer, index=False, sheet_name='Weather Data')
        output.seek(0)
        return send_file(output, as_attachment=True, download_name=f"{filename_base}.xlsx",
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    # Export PDF
    elif filetype == 'pdf':
        output = BytesIO()
        pdf = canvas.Canvas(output, pagesize=letter)
        pdf.setFont("Helvetica", 10)

        textobject = pdf.beginText(40, 750)
        textobject.textLine(f"NEA Weather Data - Station: {cached_metadata['station']}")
        textobject.textLine(f"Date: {cached_metadata['date']}   Time: {cached_metadata['start']} - {cached_metadata['end']}")
        textobject.textLine(" ")
        textobject.textLine("-----------------------------------------------------------")
        textobject.textLine(" ")

        for i, row in cached_df.iterrows():
            textobject.textLine(str(row.to_dict()))
            if textobject.getY() < 50:  # new page
                pdf.drawText(textobject)
                pdf.showPage()
                textobject = pdf.beginText(40, 750)
        pdf.drawText(textobject)
        pdf.save()
        output.seek(0)

        return send_file(output, as_attachment=True, download_name=f"{filename_base}.pdf",
                         mimetype='application/pdf')

    return "Invalid export format. Use /export/csv, /export/excel, or /export/pdf."


if __name__ == '__main__':
    app.run(debug=True)
