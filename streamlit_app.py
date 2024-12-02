import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json
import random
import string

st.set_page_config(layout="wide")

#session states
if "search_query" not in st.session_state:
    st.session_state.search_query = ""

if "selected_categories" not in st.session_state:
    st.session_state.selected_categories = []

if "selected" not in st.session_state: #state of whether we have selected an item (true) or are looking (false)
    st.session_state.selected = False

if "selected_index" not in st.session_state: #row number in large database of selected index
    st.session_state.selected_index = 0

if "previous_index" not in st.session_state: #row number in large database of selected index
    st.session_state.previous_index = -1 #must be different from starting selected index

if "changes" not in st.session_state:
    st.session_state.changes = {} #changes to push when we send batch data

if "rerun_action" not in st.session_state:
    st.session_state.rerun_action = True

if "checked_out" not in st.session_state:
    st.session_state.checked_out = False

if "new_item_entry" not in st.session_state:
    st.session_state.new_item_entry = False

if "new_item_like" not in st.session_state:
    st.session_state.new_item_like = None

# Load JSON credentials from the TOML file
@st.cache_data
def load_credentials_from_toml():
    """Load and parse the JSON credentials from a TOML file."""
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
def fetch_sheet_data(_service, spreadsheet_id, sheet_name):
    """Fetches data from the Google Sheet and returns it as a Pandas DataFrame."""
    sheet = _service.spreadsheets()
    result = sheet.values().get(spreadsheetId=spreadsheet_id, range=sheet_name).execute()
    values = result.get("values", [])
    
    if values:
        columns = []
        for value in values[0]:
            columns.append(str(value).lower())
        df = pd.DataFrame(values[1:], columns=columns)  # First row as column names
    else:
        df = pd.DataFrame()  # Empty DataFrame if no data
    return df

def update_rows(_service, spreadsheet_id, sheet_name, rows_dict):
    """
    Updates multiple rows in the Google Sheet based on a dictionary where keys are row indices
    and values are rows from a Pandas DataFrame.
    
    Args:
        _service: Google Sheets API service instance.
        spreadsheet_id: ID of the Google Sheet.
        sheet_name: Name of the sheet to update.
        rows_dict: Dictionary where keys are row indices (0-based) and values are pd.Series (rows from DataFrame).
    """
    # Prepare the batch update data
    data = []
    for index, row in rows_dict.items():
        # Convert the row to a list
        updated_row = row.tolist()
        # Calculate the range for this row (1-based indexing in Sheets, +2 for header)
        range_to_update = f"{sheet_name}!A{index + 2}"
        # Append this update to the batch data
        data.append({
            "range": range_to_update,
            "values": [updated_row]
        })

    # Perform batch update to Google Sheets
    if data:
        body = {
            "valueInputOption": "RAW",
            "data": data
        }
        _service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()
    st.session_state.changes = {}

def get_new_id(key=None):
    existing_ids = st.session_state.data['id'].tolist()
    
    # Generate a random new ID if no key is provided
    if key is None:
        while True:
            new_key = ''.join(random.choices(string.ascii_uppercase, k=12))
            new_id = f"{new_key}-0"
            if new_id not in existing_ids:
                return new_id

    # If key is provided, extract the base part and current number
    if '-' in key:
        base_key, current_number = key.rsplit('-', 1)
    else:
        base_key, current_number = key, "0"

    # Validate and parse the current number
    current_number = int(current_number) if current_number.isdigit() else 0

    # Find all IDs that start with the given base key
    matching_ids = [id for id in existing_ids if id.startswith(base_key + "-")]

    # Extract numeric suffixes from matching IDs
    numbers = []
    for match in matching_ids:
        _, num = match.rsplit('-', 1)
        if num.isdigit():
            numbers.append(int(num))

    # Determine the next available number
    next_number = max(numbers, default=current_number) + 1

    # Return the next available ID
    return f"{base_key}-{next_number}"


st.markdown("""
    <style>
    /* Apply monospace font to all Streamlit buttons */
    .stButton > button {
        font-family: "Courier New", monospace !important; /* Enforce monospace font */
        font-size: 24px !important; /* Set font size */
        font-weight: bold !important; /* Make text bold */
        color: black !important; /* Set text color */
        background-color: #F0F2F6 !important;  /* Set background color */
        border: 1px solid #ddd !important;  /* Set border */
        border-radius: 5px !important;  /* Set rounded corners */
        padding: 0px 20px !important;  /* Padding inside the button */
        cursor: pointer !important;  /* Pointer cursor on hover */
    }
    /* Button hover effect */
    .stButton > button:hover {
        background-color: #FF4B4B !important;  /* Hover color */
    }
    </style>
""", unsafe_allow_html=True)

# Function to format row data into a button label
def format_row(row):
    def format_field(field, length):
        """Format a field to a fixed length, truncating or padding as necessary."""
        content = str(field)[:length-3]  # Truncate if exceeds length
        content = content.ljust(length, '\u00A0')  # Pad with non-breaking spaces
        return content

    # Create the formatted fields
    name_field = format_field(row['name'], 30)
    id_field = format_field(f"ID: {row['id']}", 20)
    qty_field = format_field(f"QTY: {row['quantity']}", 20)
    loc_field = format_field(f"LOC: {row['location']}", 20)

    # Combine fields into a single string for button text
    return f"`{name_field}{id_field}{qty_field}{loc_field}`"

# Function to display a row as a button with Streamlit's st.button
def display_row(row, index):
    # Format the button label with the custom function
    button_label = format_row(row)
    button_clicked = st.button(button_label, key=f"button_{index}")
    # Check if the button was clicked
    if button_clicked:
        st.session_state.selected = True
        st.session_state.selected_index = index
        st.rerun()

# Function to handle row selection
def handle_row_selection(index):
    if not st.session_state.previous_index == index: #write the undo version copy if new item selected
        st.session_state.previous_copy = st.session_state.data.iloc[index].copy()
    st.session_state.current_copy = st.session_state.data.iloc[index].copy()
    st.session_state.previous_index = index     

    def generate_message(columns):
        row_data = st.session_state.data.loc[index, columns].to_dict()
        message_parts = [
            f"{col.upper()}:\u00A0\u00A0\u00A0**{row_data[col]}**"
            for col in columns
        ]
        # Join the parts with four spaces
        message = "\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0".join(message_parts)
        # Wrap in the st.success format
        return f"\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0{message}"

    if mode == "Viewing":
        # Show the dataframe for editing using st.data_editor
        edited_df = st.data_editor(
            pd.DataFrame([st.session_state.current_copy]),  # Wrap the row in a DataFrame for data_editor
            use_container_width=True
        )

        # Function placeholders for button actions
        def save_changes():         
            st.session_state.data.loc[index] = edited_df.iloc[0]
            st.session_state.changes[index] = edited_df.iloc[0].copy()
            st.success("Changes saved.")

        # Layout for the buttons in 3 columns
        col1, col2, col3 = st.columns([1,1,3])
        with col1:
            save_button = st.button("Save Changes")
            if save_button:
                save_changes()
        with col2:
            new_item_button = st.button("New Item Like This Item")
            if new_item_button:
                st.session_state.new_item_like = index 
                st.session_state.new_item_entry = True
                st.rerun()
                

    elif mode == "Deleting":
        col1, col2 = st.columns([1,15])
        with col1:
            undo = st.button("Undo")
            if undo:
                st.session_state.data.loc[index] = st.session_state.previous_copy
                st.session_state.changes[index] = st.session_state.previous_copy
                st.write("Undone!")
            else:
                if st.session_state.rerun_action == True:
                    st.session_state.data.iloc[index]["quantity"] = int(st.session_state.data.iloc[index]["quantity"]) - 1
                    st.session_state.changes[index] = st.session_state.data.iloc[index].copy()
        with col2:
            string = generate_message(["name", "id", "quantity"])
            if st.session_state.rerun_action == True:
                st.success(f"DELETE ITEM SUCCESS:\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0{string}")
            else:
                st.info(f"Selected:\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0{string}")

    elif mode == "Adding":
        col1, col2 = st.columns([1,15])
        with col1:
            undo = st.button("Undo")
            if undo:
                st.session_state.data.loc[index] = st.session_state.previous_copy
                st.session_state.changes[index] = st.session_state.previous_copy
                st.write("Undone!")
            else:
                if st.session_state.rerun_action == True:
                    st.session_state.data.iloc[index]["quantity"] = int(st.session_state.data.iloc[index]["quantity"]) + 1
                    st.session_state.changes[index] = st.session_state.data.iloc[index].copy()
        with col2:
            string = generate_message(["name", "id", "quantity"])
            if st.session_state.rerun_action == True:
                st.success(f"ADD ITEM SUCCESS:\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0{string}")
            else:
                st.info(f"Selected:\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0{string}")

    elif mode == "Checking In":
        col1, col2 = st.columns([1,15])
        with col1:
            undo = st.button("Undo")
            if undo:
                st.session_state.data.loc[index] = st.session_state.previous_copy
                st.session_state.changes[index] = st.session_state.previous_copy
                st.write("Undone.")
            else:
                if st.session_state.rerun_action == True:
                    st.session_state.data.iloc[index]["owner"] = "none"
                    st.session_state.changes[index] = st.session_state.data.iloc[index].copy()
        with col2:
            string = generate_message(["name", "id", "owner"])
            if st.session_state.rerun_action == True:
                st.success(f"CHECKED IN SUCCESS:\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0{string}")
            else:
                st.info(f"Selected:\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0{string}")

    elif mode == "Checking Out":
        col1, col2 = st.columns([1,15])
        with col1:
            undo = st.button("Undo")
            if undo:
                st.session_state.data.loc[index] = st.session_state.previous_copy
                st.session_state.changes[index] = st.session_state.previous_copy
                st.write("Undone.")
        with col2:
            string = generate_message(["name", "id", "owner"])
            if st.session_state.rerun_action == True:
                st.info(f"CHECKING OUT:\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0{string}")
            else:
                st.info(f"Selected:\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0{string}")
        
        with st.form(key="check_out_form"):
            owner = st.text_input("TO: Owner email, name, or ID:", key="blah")
            submit = st.form_submit_button("Submit")
            
            if submit:
                st.session_state.checked_out = True

        if st.session_state.checked_out:
            if not undo:
                st.session_state.data.iloc[index]["owner"] = owner
                st.session_state.changes[index] = st.session_state.data.iloc[index].copy()
                st.success(
                    f"CHECKING OUT SUCCESS:{string} \u00A0\u00A0\u00A0\u00A0------------> to new owner:\u00A0\u00A0\u00A0\u00A0**{owner}**"
                )
            st.session_state.checked_out = False
        
    st.session_state.rerun_action = True #rerun the action is ok again

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
#try:
if "data" not in st.session_state:
    st.session_state.data = fetch_sheet_data(service, SPREADSHEET_ID, SHEET_NAME)

# Ensure required columns exist
if not {"categories", "id", "name", "barcode"}.issubset(st.session_state.data.columns):
    st.error(
        "The sheet must have the required columns: 'categories', 'id', 'name', 'barcode'"
    )
    st.stop()
else:
    # Filters and search
    c11, c12, c13 = st.columns([1, 1, 2.5])
    with c11:
        push_changes = st.button("**Push My Changes (Save)**")
        if push_changes:
            update_rows(service, SPREADSHEET_ID, SHEET_NAME, st.session_state.changes)
            if st.session_state.selected:
                st.session_state.rerun_action = False
            else:    
                st.session_state.rerun_action = True
    with c12:
        pull_changes = st.button("**Pull Server Changes (Discard my changes)**")
        if pull_changes:
            st.session_state.data = fetch_sheet_data(service, SPREADSHEET_ID, SHEET_NAME)
            st.session_state.changes = {}
            if st.session_state.selected:
                st.session_state.rerun_action = False
            else:    
                st.session_state.rerun_action = True

    st.divider()
    st.subheader("Filter and Search")

    # Category filter
    categories_list = (
        st.session_state.data["categories"]
        .str.split(",")
        .explode()
        .str.strip()
        .dropna()
        .unique()
    )
    c1, c2, c3, c4 = st.columns([5, 5, 1, 1])
    with c1:
        def submit():
            st.session_state.search_query = st.session_state.search_widget
            st.session_state.search_widget = ""
            st.session_state.selected = False
            st.session_state.rerun_action = True

        st.text_input("Search", key="search_widget", on_change=submit)
        search_query = st.session_state.search_query

    with c2:
        #Category filter
        def submit():
            st.session_state.selected_categories = st.session_state.select_widget
            st.session_state.selected = False
            st.session_state.search_widget = ""
            st.session_state.search_query = st.session_state.search_widget
            st.session_state.rerun_action = False

        st.multiselect("Filter by Categories", categories_list, key="select_widget", on_change=submit)
        selected_categories = st.session_state.selected_categories

    def mode_change():
        if st.session_state.selected:
            st.session_state.rerun_action = False
        else:    
            st.session_state.rerun_action = True
        st.session_state.selected = False
        st.session_state.search_widget = ""
        st.session_state.search_query = st.session_state.search_widget
        

    with c3:
        and_or = st.selectbox("AND/OR", options=["AND", "OR"], on_change=mode_change)
    with c4:
        result_limit = st.number_input("Results per page", min_value=1, value=100, on_change=mode_change)
    
    modes = ["Viewing", "Deleting", "Adding", "Checking In", "Checking Out"]
    mode = st.selectbox("Choose an action", modes, index=modes.index("Viewing"), on_change=mode_change)

    if mode == "Viewing":
        st.info("**You are viewing. Scan a barcode or search a value to find items. View their contents and make changes.**")
    elif mode == "Deleting":
        st.info("**You are deleting. Scan a barcode or search a value to find items. The quantity column will decrement by 1 automatically.**")
    elif mode == "Adding":
        st.info("**You are adding. Scan a barcode or search a value to find items. The quantity column will increment by 1 automatically.**")
    elif mode == "Checking In":
        st.info("**You are checking in. Scan a barcode or search a value to find items. The owner column will become none.**")
    elif mode == "Checking Out":
        st.info("**You are checking out. Scan a barcode or search a value to find items. Enter the owner into the textbox below to set the owner column.**")

    # Filtering function
    def filter_data(df):
        filtered_df = df.copy()
        filtered_df["original_index"] = filtered_df.index

        # Search query filter
        if st.session_state.search_query:
            filtered_df = filtered_df[
                filtered_df.apply(
                    lambda row: st.session_state.search_query.lower() in row.drop("original_index").to_string().lower(), axis=1
                )
            ]

        # Categories filter (AND/OR logic)
        if st.session_state.selected_categories:
            if and_or == "AND":
                # Item must be in all selected categories
                filtered_df = filtered_df[
                    filtered_df["categories"].apply(
                        lambda x: all(cat in map(str.strip, x.split(",")) for cat in st.session_state.selected_categories)
                    )
                ]
            elif and_or == "OR":
                # Item must be in any of the selected categories
                filtered_df = filtered_df[
                    filtered_df["categories"].apply(
                        lambda x: any(cat in map(str.strip, x.split(",")) for cat in st.session_state.selected_categories)
                    )
                ]

        return filtered_df

    
    st.divider()

    # Apply filters and display results
    if not st.session_state.new_item_entry:
        filtered_data = filter_data(st.session_state.data)
        def search_info_bar():
            if not st.session_state.selected_categories == []:
                st.info(f"With search terms: {st.session_state.search_query} and matching categories: {st.session_state.selected_categories}")
            else:
                st.info(f"With search terms: {st.session_state.search_query}")

        #check length of DF to determine action
        if len(filtered_data) == 0:
            st.subheader(f"No Results:")
            search_info_bar()
            

        elif len(filtered_data) == 1:
            st.session_state.selected = True
            index = filtered_data.iloc[0]["original_index"]
            st.session_state.selected_index = index

        
        #actions
        if not st.session_state.selected and not len(filtered_data) == 0: #list of potential choices
            st.subheader(f"Filtered Results: Showing of {min(result_limit, len(filtered_data))} of {len(filtered_data)}")
            search_info_bar()


            # Display rows up to the result limit
            head_filter = filtered_data.head(result_limit)
            for index, row in head_filter.iterrows():
                original_index = row["original_index"]
                try:
                    display_row(row, original_index)
                except Exception as e:
                    st.error(f"Duplicate ID found at row {original_index+1}. Please modify in google sheets.")

        elif st.session_state.selected: #select the choice
            st.subheader(f"Selected Item: {st.session_state.data.iloc[st.session_state.selected_index]["name"]}")
            handle_row_selection(st.session_state.selected_index)
    else:
        st.subheader("Inputting New Item:")
        st.info("Please input data with the data editor, then click cancel or save. It will add a new row to the spreadsheet.")

        # Determine the data to display in the editor
        if st.session_state.get("new_item_like") is not None:
            # Use the row from the main dataframe as a template
            template_row = st.session_state.data.loc[st.session_state.new_item_like].copy()
            key = template_row.loc["id"]
            template_row.loc["id"] = get_new_id(key=key)
            edited_df = st.data_editor(
                pd.DataFrame([template_row]),  # Wrap the row in a DataFrame
                use_container_width=True,
            )
        else:
            # Create an empty row with the same columns for new input
            empty_row = pd.DataFrame([{col: "" for col in st.session_state.data.columns}])
            edited_df = st.data_editor(
                empty_row,  # Use the empty row as the base
                use_container_width=True,
            )

        # Function placeholders for button actions
        def save_new_item():
            new_row = edited_df.iloc[0]  # Extract the row from the editor (first row, as it's single)
            st.session_state.data = st.session_state.data.append(new_row, ignore_index=True)
            st.session_state.changes[len(st.session_state.data) - 1] = new_row.copy()  # Track the new row's changes
            st.session_state.new_item_like = None  # Reset the new item session key
            st.session_state.new_item_entry = False  # Reset the new item session key
            st.rerun()


        def cancel_new_item():
            st.session_state.new_item_like = None  # Reset the new item session key
            st.session_state.new_item_entry = False  # Reset the new item session key
            st.rerun()

        # Layout for the buttons in 2 columns
        col1, col2, col3 = st.columns([1, 1, 3])
        with col1:
            save_button = st.button("Save New Item")
            if save_button:
                save_new_item()
        with col2:
            cancel_button = st.button("Cancel")
            if cancel_button:
                cancel_new_item()



#except Exception as e:
    #st.error(f"Error fetching sheet data: {e}")
