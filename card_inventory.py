import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json
import random
import string
import barcode_generator

def run_top_to_bottom():
    #session states
    if "search_query" not in st.session_state:
        st.session_state.search_query = ""

    if "pills_query" not in st.session_state:
        st.session_state.pills_query = None

    if "viewing_pills_query" not in st.session_state:
        st.session_state.viewing_pills_query = None

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

    if "new_item_entry" not in st.session_state:
        st.session_state.new_item_entry = False

    if "barcode_print_list" not in st.session_state:
        st.session_state.barcode_print_list = [] #stored as list of [int: quantity to print, str: barcode text]

    if "print_barcodes_in_viewing" not in st.session_state:
        st.session_state.print_barcodes_in_viewing = False

    if "click_history" not in st.session_state:
        st.session_state.click_history = []

    if "first_item_using" not in st.session_state:
        st.session_state.first_item_using = True

    if "hierarchy" not in st.session_state:
        st.session_state.hierarchy = {
            "machine": 1,
            "shelf": 1,
            "cart": 1,
            "tray": 2,
            "box": 3,
            "separator":4,
            "location": 100
        }

    if "previous_type" not in st.session_state:
        st.session_state.previous_type = None

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
        id_field = format_field(f"ID: {row['id']}", 20)
        name_field = format_field(f"NAME: {row['name']}", 20)
        type_field = format_field(f"TYPE: {row['type']}", 20)
        parent_field = format_field(f"PARENT: {row['parent']}", 25)
        child_field = format_field(f"CHILD: {row['child']}", 25)
        loc_field = format_field(f"LOC: {row['location']}", 20)

        # Combine fields into a single string for button text
        return f"`{id_field}{name_field}{type_field}{parent_field}{child_field}{loc_field}`"

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

    def locate(index):
        # Extract the DataFrame from session state
        df = st.session_state.data

        # Initialize variables to store type and location details
        path_details = []
        
        # Start from the given index
        current_index = index
        
        while current_index is not None:
            # Get the current row
            row = df.loc[current_index]
            
            # Extract Type and Location
            try:
                item_type = row["type"].upper()
            except:
                item_type = None
            item_id = row["id"].upper()
            item_name = row["name"]
            location = row["location"]
                

            if location == "" or location is None:          
                if item_name == "" or item_name is None:  
                    path_details.append(f"{item_type}: {item_id} in slot: None \n")
                else:
                    path_details.append(f"{item_type}, {item_name}: {item_id} in slot: None. \n")
            else:          
                if item_name == "" or item_name is None:  
                    path_details.append(f"{item_type}: {item_id} in slot {location} \n")
                else:
                    path_details.append(f"{item_type}, {item_name}: {item_id} in slot {location} \n")
            
            # Find the parent ID and locate the parent index
            parent_id = row["parent"]
            if pd.notna(parent_id) and parent_id.strip():
                parent_index = df.index[df["id"] == parent_id].tolist()
                current_index = parent_index[0] if parent_index else None
            else:
                # No parent exists, terminate the loop
                current_index = None
        
        # Construct the final string by joining path details in reverse order
        path_list = reversed(path_details)
        return path_list


    # Function to handle row selection
    def handle_row_selection(index):
        st.session_state.current_copy = st.session_state.data.iloc[index].copy()

        def display_children():
            st.caption(f"Children belonging to {st.session_state.data.iloc[st.session_state.selected_index]['id']}")
            data = st.session_state.data
            child_ids_csv = data.loc[st.session_state.selected_index, "child"]
            
            if not child_ids_csv:  # If no children, display a message and return
                st.info("No children found.")
                return
            # Convert the CSV string of child IDs into a list
            child_ids = child_ids_csv.split(",")
            # Filter rows with IDs matching the child IDs
            filtered_rows = data[data["id"].astype(str).isin(child_ids)]
            for index, row in filtered_rows.iterrows():
                display_row(row, index)

        def display_parent():
            st.divider()
            st.caption(f"Parent of {st.session_state.data.iloc[st.session_state.selected_index]['id']}")
            data = st.session_state.data
            parent_id = data.loc[st.session_state.selected_index, "parent"]
            
            if not parent_id:  # If no children, display a message and return
                st.info("No parent found.")
                return
            # Filter rows with IDs matching the child IDs
            filtered_rows = data[data["id"].astype(str).isin([parent_id])]
            for index, row in filtered_rows.iterrows():
                display_row(row, index)

        if mode == "Viewing":
            # Show the dataframe for editing using st.data_editor
            '''
            edited_df = st.dataframe(
                pd.DataFrame([st.session_state.current_copy]),  # Wrap the row in a DataFrame for data_editor
                use_container_width=True
            )
            '''
            st.caption(f"**Location**")  
            for loc in locate(index):
                st.caption(loc)

            
            def viewing_pills_submit():
                st.session_state.viewing_pills_query = st.session_state.viewing_pills_widget
                st.session_state.viewing_pills_widget = None
                st.session_state.rerun_action = True
                if st.session_state.viewing_pills_query == "**Print barcodes of this item**":
                    st.session_state.print_barcodes_in_viewing = True

            st.pills("More Actions:", ["**Print barcodes of this item**"], key="viewing_pills_widget", selection_mode="single", default=None, on_change=viewing_pills_submit)
            viewing_pills_query = st.session_state.viewing_pills_query

            if st.session_state.print_barcodes_in_viewing:
                def save_to_print_queue():
                    st.session_state.print_barcodes_in_viewing = False
                    st.session_state.barcode_print_list.append([quantity_to_print, f"{st.session_state.current_copy.loc['id']}"])
                def cancel_print():
                    st.session_state.print_barcodes_in_viewing = False

                quantity_to_print = st.number_input("Quantity to print", value=1)
                st.button("Save to print queue", on_click=save_to_print_queue)
                st.button("Cancel", on_click=cancel_print)

            
            display_parent()
            display_children()

                    

        elif mode == "Deleting":
            # col1, col2 = st.columns([1,13])
            # with col1:
            #     undo = st.button("Undo")
            #     if undo:
            #         st.session_state.data.loc[index] = st.session_state.previous_copy
            #         st.session_state.changes[index] = st.session_state.previous_copy
            #         st.write("Undone!")
            #     else:
            #         if st.session_state.rerun_action == True:
            #             st.session_state.data.iloc[index]["quantity"] = int(st.session_state.data.iloc[index]["quantity"]) - 1
            #             st.session_state.changes[index] = st.session_state.data.iloc[index].copy()
            # with col2:
            #     string = generate_message(["name", "id", "quantity"])
            #     if st.session_state.rerun_action == True:
            #         st.success(f"DELETE ITEM SUCCESS:\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0{string}")
            #     else:
            #         st.info(f"Selected:\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0{string}")
            st.info("Delete function not written yet")

        elif mode == "Using":
            def verify_proper_action(batch_type, end_type):
                hierarchy = st.session_state.hierarchy
                if hierarchy[batch_type] - hierarchy[end_type] == 1: #check if we are placing an item of status exactly 1 less into parent. Otherwise fail.
                    return True                            
                else:
                    st.error(f"Did not complete action. Cannot place type {batch_type} in {end_type}.") 
                    st.session_state.click_history = []
                    st.session_state.first_item_using = True
                    return False
                
            def remove_children_from_other_parents(child_ids):
                for idx, row in st.session_state.data.iterrows():
                    existing_child_ids = row["child"]
                    if pd.notna(existing_child_ids) and existing_child_ids.strip():
                        child_list = existing_child_ids.split(",")
                        # Filter out any IDs in the child_ids list
                        updated_child_list = [id_ for id_ in child_list if id_ not in child_ids]
                        if len(updated_child_list) != len(child_list):  # Only update if there was a change
                            # Update the dataframe
                            st.session_state.data.loc[idx, "child"] = ",".join(updated_child_list)
                            st.session_state.changes[idx] = st.session_state.data.iloc[idx].copy()


            def get_location_associate(idx):
                df = st.session_state.data
                loc_id = df.loc[idx,"id"]
                associate_id = '-'.join(loc_id.split('-')[:-1]) if loc_id.count('-') > 1 else loc_id
                associate_idx = df.index[df['id'] == associate_id].tolist()[0] if any(df['id'] == associate_id) else None
                associate_type = st.session_state.data.loc[associate_idx, "type"]
                return associate_idx, associate_id, associate_type
            
            def remove_existing_relationship_at(idx):
                df = st.session_state.data
                existing_child_id = df.loc[idx, "child"].strip()
                existing_child_idx = df.index[df['id'] == existing_child_id].tolist()[0] if any(df['id'] == existing_child_id) else None
                if existing_child_idx is not None:
                    df.loc[existing_child_idx, "parent"] = "" #remove the existing child's parent in column
                    df.loc[existing_child_idx, "location"] = "" #remove the existing child's location in column
                    st.session_state.changes[existing_child_idx] = st.session_state.data.iloc[existing_child_idx].copy()
                    remove_children_from_other_parents([existing_child_id]) #remove the child from all parents
            
            this_type = st.session_state.current_copy.loc["type"].lower()
            ids_string = ""
            for ind in st.session_state.click_history:
                ids_string+=f"{st.session_state.data.iloc[ind]['id']}, "
            #check if we are starting a batch. Don't do any commands if so
            if st.session_state.first_item_using:
                #make sure its not a toplevel
                if this_type == "location":
                    st.session_state.click_history.append(index)
                    st.session_state.first_item_using = False
                    st.info(f"Remembering location. Scan a unit to place into it.")
                else:
                    st.session_state.click_history.append(index)
                    st.session_state.first_item_using = False
                    st.info(f"Remembering history for batch movement. So far: {st.session_state.data.iloc[index]['id']}. Scan a larger unit to place all these items in it. Will index location starting at 1 if larger item scanned, or scan its location to start there.")

            #if we aren't, look for command execution signs
            else:
                #check if same item scanned
                if not st.session_state.previous_type == "location" and not this_type == "location":
                    if st.session_state.previous_index == index:
                        st.info(f"Remembering history. So far: {ids_string}. Scan a larger unit to place all these items in it.")
                    #if not, check if same type
                    elif st.session_state.previous_type.lower() == this_type:
                        if index not in st.session_state.click_history:
                            st.session_state.click_history.append(index)
                            ids_string+=f"{st.session_state.data.iloc[index]['id']}, "
                        st.info(f"Remembering history. So far: {ids_string}. Scan a larger unit to place all these items in it.")
                    
                    #we can now execute a command
                    else:
                        if verify_proper_action(st.session_state.previous_type.lower(), this_type):
                            # Get the parent ID from the "id" column at the parent_index
                            parent_id = st.session_state.data.loc[index, "id"]
                            updated_click_history = []
                            associates_to_update = []
                            df = st.session_state.data

                            # Update the "parent" column for each index in click_history
                            additional_increment = 0
                            for i, child_index in enumerate(st.session_state.click_history):
                                associate_id = f"{parent_id}-{i}"
                                associate_idx = df.index[df['id'] == associate_id][0] if any(df['id'] == associate_id) else None #get index of location
                                if associate_idx is None:
                                    child_ids = st.session_state.data.loc[updated_click_history, "id"].tolist()
                                    st.warning(f"Unable to assign the whole batch to this item. Only assigned {child_ids}.")
                                    break
                                else:
                                    remove_existing_relationship_at(associate_idx)
                                    associates_to_update.append(associate_idx)
                                    updated_click_history.append(child_index)

                                st.session_state.data.loc[child_index, "parent"] = parent_id
                                st.session_state.changes[child_index] = df.iloc[child_index].copy()
                            
                            child_ids = st.session_state.data.loc[updated_click_history, "id"].tolist()
                            remove_children_from_other_parents(child_ids)

                            for associate_idx, child_idx in zip(associates_to_update, updated_click_history):
                                st.session_state.data.loc[associate_idx, "child"] = df.loc[child_idx, "id"] #set location's child
                                st.session_state.data.loc[child_idx, "location"] = df.loc[associate_idx, "location"] #set location's child
                                st.session_state.changes[child_idx] = df.iloc[child_idx].copy()
                                st.session_state.changes[associate_idx] = df.iloc[associate_idx].copy()

                            # Get the list of child IDs based on click_history
                            existing_child_ids = st.session_state.data.loc[index, "child"]
                            if pd.notna(existing_child_ids) and existing_child_ids.strip():
                                current_child_ids = existing_child_ids.split(",")
                            else:
                                current_child_ids = []

                            updated_child_ids = list(set(current_child_ids + list(map(str, child_ids))))

                            # Update the "child" column for the parent index with a CSV list of updated child IDs
                            st.session_state.data.loc[index, "child"] = ",".join(updated_child_ids)
                            st.session_state.changes[index] = st.session_state.data.iloc[index].copy()

                            st.session_state.click_history = []
                            st.session_state.first_item_using = True
                            update_rows(service, SPREADSHEET_ID, SHEET_NAME, st.session_state.changes)
                            st.success(f"Assigned {child_ids} to {parent_id}")

                elif st.session_state.previous_type == "location" and not this_type == "location":
                    associate_idx, associate_id, associate_type = get_location_associate(st.session_state.previous_index)
                    if verify_proper_action(this_type, associate_type):
                        remove_existing_relationship_at(st.session_state.previous_index)
                        #assign the current scan to the location and reset (add this_type's ID to location's child and the location's associated item's Child)
                        remove_children_from_other_parents([st.session_state.current_copy.loc["id"]])
                        st.session_state.data.loc[st.session_state.previous_index, "child"] = st.session_state.current_copy.loc["id"] #set location's child
                        st.session_state.changes[st.session_state.previous_index] = st.session_state.data.iloc[st.session_state.previous_index].copy()
                        existing_child_ids = st.session_state.data.loc[associate_idx, "child"]
                        if pd.notna(existing_child_ids) and existing_child_ids.strip():
                            current_child_ids = existing_child_ids.split(",")
                        else:
                            current_child_ids = []

                        new_child_id = str(st.session_state.current_copy.loc["id"])
                        updated_child_ids = list(set(current_child_ids + [new_child_id]))

                        st.session_state.data.loc[associate_idx, "child"] = ",".join(updated_child_ids)
                        st.session_state.data.loc[index, "parent"] = associate_id   #set scanned
                        st.session_state.data.loc[index, "location"] = st.session_state.data.loc[st.session_state.previous_index, "location"] #set child location column
                        st.session_state.changes[index] = st.session_state.data.iloc[index].copy()
                        st.session_state.changes[associate_idx] = st.session_state.data.iloc[associate_idx].copy()


                        st.session_state.click_history = []
                        st.session_state.first_item_using = True
                        st.success(f"Assigned {st.session_state.current_copy.loc['id']} to {associate_id}")
                        update_rows(service, SPREADSHEET_ID, SHEET_NAME, st.session_state.changes)
                        
                elif not st.session_state.previous_type == "location" and this_type == "location":
                    associate_idx, associate_id, associate_type = get_location_associate(index)
                    prev_idx = st.session_state.previous_index
                    if verify_proper_action(st.session_state.previous_type, associate_type):
                        remove_existing_relationship_at(index)
                        remove_children_from_other_parents([st.session_state.data.loc[prev_idx, "id"]])
                        #assign the current scan to the location and reset (add this_type's ID to location's child and the location's associated item's Child)
                        st.session_state.data.loc[index, "child"] = st.session_state.data.loc[prev_idx, "id"] #set location's child
                        st.session_state.changes[index] = st.session_state.data.iloc[index].copy()

                        existing_child_ids = st.session_state.data.loc[associate_idx, "child"]
                        if pd.notna(existing_child_ids) and existing_child_ids.strip():
                            current_child_ids = existing_child_ids.split(",")
                        else:
                            current_child_ids = []
                        new_child_id = str(st.session_state.data.loc[prev_idx, "id"])
                        updated_child_ids = list(set(current_child_ids + [new_child_id]))

                        st.session_state.data.loc[associate_idx, "child"] = ",".join(updated_child_ids)
                        st.session_state.data.loc[prev_idx, "parent"] = associate_id   #set scanned
                        st.session_state.data.loc[prev_idx, "location"] = st.session_state.data.loc[index, "location"] #set child location column
                        st.session_state.changes[prev_idx] = st.session_state.data.iloc[prev_idx].copy()
                        st.session_state.changes[associate_idx] = st.session_state.data.iloc[associate_idx].copy()

                        st.session_state.click_history = []
                        st.session_state.first_item_using = True
                        st.success(f"Assigned {st.session_state.data.loc[prev_idx, 'id']} to {associate_id}")
                        update_rows(service, SPREADSHEET_ID, SHEET_NAME, st.session_state.changes)

                else:
                    st.warning("Did not complete action. Cannot assign location to location.")
                    st.session_state.click_history = []
                    st.session_state.first_item_using = True
                    

            
        st.session_state.rerun_action = True #rerun the action is ok again
        st.session_state.previous_index = index     
        st.session_state.previous_type = st.session_state.current_copy.loc["type"]

    # Load credentials and authenticate
    try:
        credentials_dict = load_credentials_from_toml()
        service = authenticate_with_service_account(credentials_dict)
    except Exception as e:
        st.error(f"Failed to load credentials or authenticate: {e}")
        st.stop()

    # Proceed to the rest of the app
    SPREADSHEET_ID = "1x5QrksNozxbZhf9GlJkWY2FtLG6-H0x7Lr6wKvGODSk"
    SHEET_NAME = "Cards"

    # Load data from Google Sheets
    #try:
    if "data" not in st.session_state:
        st.session_state.data = fetch_sheet_data(service, SPREADSHEET_ID, SHEET_NAME)
    elif st.session_state.data is None:
        st.session_state.data = fetch_sheet_data(service, SPREADSHEET_ID, SHEET_NAME)

    # Ensure required columns exist
    if not {"id", "name", "type", "parent", "child", "barcode", "location"}.issubset(st.session_state.data.columns):
        st.error(
            "The sheet must have the required columns: 'id', 'name', 'type', 'parent', 'child', 'barcode', 'location'"
        )
        st.stop()
    else:
        # Filters and search
        def pills_submit():
                st.session_state.pills_query = st.session_state.pills_widget
                st.session_state.pills_widget = None
                st.session_state.selected = False
                st.session_state.rerun_action = True
                if st.session_state.pills_query == "**Download Gathered Barcodes**":
                    barcode_generator.download_qr_code_pdf(st.session_state.barcode_print_list)
                    st.session_state.barcode_print_list = [] #clear data


        st.pills("Main Actions:", ["**Download Gathered Barcodes**"], key="pills_widget", selection_mode="single", default=None, on_change=pills_submit)
        pills_query = st.session_state.pills_query

        st.divider()
        st.subheader("Filter and Search")

        # Category filter
        categories_list = ("shelf", "machine", "cart", "tray", "box", "separator", "location")

        c1, c2, c3, c4 = st.columns([5, 5, 1.5, 1.5])
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

            st.multiselect("Filter by Type", categories_list, key="select_widget", on_change=submit)
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
        
        modes = ["Viewing", "Deleting", "Using"]
        mode = st.selectbox("Choose an action", modes, index=modes.index("Viewing"), on_change=mode_change)

        if mode == "Viewing":
            st.info("**You are viewing. Scan a barcode or search a value to find items. View their data.**")
        elif mode == "Deleting":
            st.info("**You are deleting. Scan a barcode or search a value to remove that item.**")
        elif mode == "Using":
            st.info("**You are using. Scan items to move them around. Scanning multiple of the same item into a higher level item will place them all together.")

        def make_new_item():
            st.session_state.new_item_entry = True

        st.button("Input a New Item", on_click=make_new_item)

        # Filtering function
        def filter_data(df):
            filtered_df = df.copy()
            filtered_df["original_index"] = filtered_df.index

            if mode == "Viewing":
                if st.session_state.search_query.strip().lower() in filtered_df["id"].astype(str).str.lower().tolist():
                    filtered_df = filtered_df[filtered_df["id"].astype(str).str.lower() == st.session_state.search_query.strip().lower()]
                else:
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
                                filtered_df["type"].apply(
                                    lambda x: all(cat.lower() in map(str.strip, x.lower().split(",")) for cat in st.session_state.selected_categories)
                                )
                            ]
                        elif and_or == "OR":
                            # Item must be in any of the selected categories
                            filtered_df = filtered_df[
                                filtered_df["type"].apply(
                                    lambda x: any(cat.lower() in map(str.strip, x.lower().split(",")) for cat in st.session_state.selected_categories)
                                )
                            ]

            elif mode == "Using":
                if st.session_state.search_query:
                    # Filter by exact match on the "id" column, case-insensitive
                    filtered_df = filtered_df[
                        filtered_df["id"].astype(str).str.lower() == st.session_state.search_query.strip().lower()
                    ]
                else:
                    filtered_df = filtered_df.iloc[0:0]  # Return empty DataFrame if no search query is provided.
            return filtered_df

        
        st.divider()

        # Apply filters and display results
        if not st.session_state.new_item_entry:
            filtered_data = filter_data(st.session_state.data)
            def search_info_bar():
                if not st.session_state.selected_categories == []:
                    st.info(f"With search terms: {st.session_state.search_query} and matching type: {st.session_state.selected_categories}")
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
                    #try:
                    display_row(row, original_index)
                    #except Exception as e:
                        #st.error(f"Duplicate ID found at row {original_index+1}. Please modify in google sheets.")

            elif st.session_state.selected: #select the choice
                st.subheader(f"Selected Item: {st.session_state.data.iloc[st.session_state.selected_index]['id']}")
                handle_row_selection(st.session_state.selected_index)
        else:
            st.subheader("Inputting New Item:")
            st.info("Please input data with the data editor, then click cancel or save. It will add a new row to the spreadsheet.")

            def get_new_id(node_type):
                """Generate a unique ID based on the type."""
                while True:
                    random_id = ''.join(random.choices(string.ascii_uppercase, k=6))
                    node_id = f"{node_type.upper()[:3]}-{random_id}"
                    # Ensure ID is unique by checking against existing DataFrame
                    if not any(st.session_state.data['id'] == node_id):
                        return node_id
                    
            def get_location_ids(node_id, quantity):
                outputs = []
                for i in range(quantity):
                    outputs.append(f"{node_id}-{i}")
                return outputs

                    
            def save_new_items(node_type, quantity, name, lsq):
                """Save new items to the session DataFrame and update the barcode list."""
                for _ in range(quantity):
                    node_id = get_new_id(node_type)
                    barcode = f"*{node_id}*"
                    ls_ids = None
                    if not lsq == 0:
                        ls_ids = get_location_ids(node_id, lsq)
                    
                    # Generate a new row for the DataFrame
                    new_row = pd.DataFrame([{
                        "id": node_id,
                        "name": name,
                        "type": node_type,
                        "parent": "",
                        "child": "",
                        "barcode": barcode,
                        "location": ""
                    }])
                    st.session_state.data = pd.concat([st.session_state.data, new_row], ignore_index=True)
                    st.session_state.barcode_print_list.append([1, node_id])
                    st.session_state.changes[len(st.session_state.data) - 1] = new_row.iloc[0].copy()

                    if not lsq == 0:
                        for i, ls_id in enumerate(ls_ids):
                            barcode = f"*{ls_id}*"
                            new_row = pd.DataFrame([{
                                "id": ls_id,
                                "name": "",
                                "type": "location",
                                "parent": "", #no parent to avoid inclusion in tree structure. Should only be assigning locations
                                "child": "",
                                "barcode": barcode,
                                "location": f"{i}"
                            }])
                            st.session_state.data = pd.concat([st.session_state.data, new_row], ignore_index=True)
                            st.session_state.barcode_print_list.append([1, ls_id])
                            st.session_state.changes[len(st.session_state.data) - 1] = new_row.iloc[0].copy()


                st.session_state.new_item_entry = False  # Reset the new item session key
                update_rows(service, SPREADSHEET_ID, SHEET_NAME, st.session_state.changes)
                st.rerun()

            def cancel_new_item():
                st.session_state.new_item_entry = False  # Reset the new item session key
                st.rerun()

            with st.form("add_items_form"):
                st.subheader("Add New Items")
                node_type = st.selectbox("Select Type", ["shelf", "cart", "machine", "tray", "box", "separator"])
                quantity = st.number_input("Quantity", min_value=1, max_value=500, step=1)
                name = st.text_input("Name (optional)")
                location_specific_quantity = st.number_input("How many location-specific tags?", min_value=0, max_value=500, step=1)
                submitted = st.form_submit_button("Submit")
                if submitted:
                    save_new_items(node_type, quantity, name, location_specific_quantity)  # Save new items to the session state and dataframe
                    st.success(f"{quantity} {node_type}(s) added successfully!")
                        
            cancel_button = st.button("Cancel")
            if cancel_button:
                cancel_new_item()

    #except Exception as e:
        #st.error(f"Error fetching sheet data: {e}")

