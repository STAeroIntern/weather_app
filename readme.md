### Update: As of Feb 2026, an API key is required for higher rate limits, it will need to be regenerated every November of the year
    * Create an account in https://data.gov.sg/signin
    * In the dashboard, click "Create API key"
        * Give it a name
        * Choose "Production" for higher rate limit
        * Description: Live weather data app for retrieval
        * Expiration = 1 Year
        * Create the key
    * Copy the API key into Notepad and save it on desktop first
    1. In venv, pip install python-dotenv
    2. Inside weather_app folder, create a file named .env
    3. It should contain: API_KEY=<created_api_key>

### 1. Install Python
### 2. Run the following below
#### Linux
    python -m venv venv
    source venv/bin/activate       
    pip install -r requirements.txt

#### Windows
    python -m venv venv
    venv\Scripts\activate          
    pip install -r requirements.txt

### 3. Run the code in terminal/command prompt: 
    python app.py
### 4. Open the app on http://127.0.0.1:5000