# app.py
from flask import Flask, render_template, request, redirect, url_for
import subprocess
import requests

app = Flask(__name__, template_folder='templates')
url = "https://api-open.data.gov.sg/v2/real-time/api/air-temperature"
url2 = "https://api-open.data.gov.sg/v2/real-time/api/wind-speed"
url3 = "https://api-open.data.gov.sg/v2/real-time/api/rainfall"
url4 = "https://api-open.data.gov.sg/v2/real-time/api/relative-humidity"
headers = {"X-Api-Key": "YOUR_SECRET_TOKEN"}
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_input = request.form['user_input']
        
        

        
        # Execute the C++ program and pass the user input
        # The C++ program would need to be compiled first (e.g., g++ my_cpp_program.cpp -o my_cpp_program)
        try:
            date = str(user_input)
            response = requests.get(url + '/?date=' + date, headers=headers)
            data  = response.json()['data']['readings']

            response2 = requests.get(url2 + '/?date=' + date, headers=headers)
            data2  = response2.json()['data']['readings']

            response3 = requests.get(url2 + '/?date=' + date, headers=headers)
            data3  = response3.json()['data']['readings']

            response4 = requests.get(url2 + '/?date=' + date, headers=headers)
            data4  = response4.json()['data']['readings']
            # Extract all records for station S103
            station_id = 'S115'
            temp_results = []
            temp_results2 = []
            temp_results3 = []
            temp_results4 = []

            for entry in data:
                timestamp = entry['timestamp']
                for station in entry['data']:
                    if station['stationId'] == station_id:
                        temp_results.append({'Date':str(timestamp)[0:10],'Time': str(timestamp)[11:19], 'Temperature': station['value']})
                        #Return the result

            for entry in data2:
                timestamp = entry['timestamp']
                for station in entry['data']:
                    if station['stationId'] == station_id:
                        temp_results2.append({'Date':str(timestamp)[0:10],'Time': str(timestamp)[11:19], 'Wind Speed': station['value']})
                        #Return the result
            for entry in data3:
                timestamp = entry['timestamp']
                for station in entry['data']:
                    if station['stationId'] == station_id:
                        temp_results3.append({'Date':str(timestamp)[0:10],'Time': str(timestamp)[11:19], 'Rainfall': station['value']})

            for entry in data4:
                timestamp = entry['timestamp']
                for station in entry['data']:
                    if station['stationId'] == station_id:
                        temp_results4.append({'Date':str(timestamp)[0:10],'Time': str(timestamp)[11:19], 'Relative Humidity': station['value']})

            # Combine them
            combined = []
            for d1, d2,d3,d4 in zip(temp_results, temp_results2,temp_results3,temp_results4):
                merged = {**d1, **d2,**d3,**d4}  # merge dictionaries
                combined.append(merged)
            # Start the HTML table
            html = '<table border="1">\n'
            html += '  <tr><th>Date</th><th>Time</th><th>Temperature</th><th>Wind Speed</th><th>Rainfall</th><th>Relative Humidity</th></tr>\n'

            # Add table rows
            for row in combined:
                html += f'  <tr><td>{row["Date"]}</td><td>{row["Time"]}</td><td>{row["Temperature"]}</td><td>{row["Wind Speed"]}</td><td>{row["Rainfall"]}</td><td>{row["Relative Humidity"]}</td></tr>\n'

            # Close the table
            html += '</table>'
            return html
        except subprocess.CalledProcessError as e:
            return f"Error executing C++ program: {e.output}"
    return render_template('template.html')

if __name__ == '__main__':
    app.run(debug=True)
