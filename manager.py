import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pathlib import Path
import json

# Load JSON credentials from the TOML file
@st.cache_data
def load_credentials_from_toml():
    """Load and parse the JSON credentials from a TOML file."""
    #toml_data = toml.load("secrets.toml")  # Adjust the file name if necessary
    json_string = st.secrets["google_service_account"]["json"]
    credentials_dict = json.loads(json_string)  # Parse the JSON string into a dictionary
    return credentials_dict

# Function to authenticate and connect to Google Sheets API
@st.cache_data
def authenticate_with_service_account(credentials_dict):
    """Authenticate with Google Sheets API using service account credentials."""
    credentials = service_account.Credentials.from_service_account_info(
        credentials_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build("sheets", "v4", credentials=credentials)
    return service

# Function to fetch data from Google Sheets (do not cache the 'service' argument)
@st.cache_data
def fetch_sheet_data(_service, spreadsheet_id, sheet_name):
    """Fetches data from the Google Sheet and returns it as a Pandas DataFrame."""
    sheet = _service.spreadsheets()
    result = sheet.values().get(spreadsheetId=spreadsheet_id, range=sheet_name).execute()
    values = result.get("values", [])
    
    if values:
        df = pd.DataFrame(values[1:], columns=values[0])  # First row as column names
    else:
        df = pd.DataFrame()  # Empty DataFrame if no data
    return df

# Streamlit app title
st.title("Inventory Management System")

# Load credentials and authenticate
try:
    credentials_dict = load_credentials_from_toml()
    service = authenticate_with_service_account(credentials_dict)
    st.success("Authenticated with Google Sheets API!")
except Exception as e:
    st.error(f"Failed to load credentials or authenticate: {e}")
    st.stop()

# Proceed to the rest of the app
SPREADSHEET_ID = "1x5QrksNozxbZhf9GlJkWY2FtLG6-H0x7Lr6wKvGODSk"
SHEET_NAME = "Inventory"  # Example Sheet Name

# Load data from Google Sheets
try:
    data = fetch_sheet_data(service, SPREADSHEET_ID, SHEET_NAME)

    # Ensure required columns exist
    if not {"categories", "ID", "name", "barcode"}.issubset(data.columns):
        st.error(
            "The sheet must have the required columns: 'categories', 'ID', 'name', 'barcode'"
        )
    else:
        # Filters and search
        st.subheader("Filter and Search")

        # Category filter
        categories_list = (
            data["categories"]
            .str.split(",")
            .explode()
            .str.strip()
            .dropna()
            .unique()
        )
        selected_categories = st.multiselect(
            "Filter by Categories", categories_list
        )

        # Search bar
        search_query = st.text_input("Search", "").lower()

        # Filtering function
        def filter_data(df):
            filtered_df = df
            if search_query:
                filtered_df = filtered_df[
                    filtered_df.apply(
                        lambda row: search_query in row.to_string().lower(), axis=1
                    )
                ]
            if selected_categories:
                filtered_df = filtered_df[
                    filtered_df["categories"].apply(
                        lambda x: any(
                            cat in map(str.strip, x.split(","))
                            for cat in selected_categories
                        )
                    )
                ]
            return filtered_df

        # Apply filters
        filtered_data = filter_data(data)

        # Show results
        st.write("Filtered Results:")
        st.dataframe(filtered_data.head(10))  # Show up to 10 results

except Exception as e:
    st.error(f"Error fetching sheet data: {e}")
