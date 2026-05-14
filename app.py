import streamlit as st
import random
import json
import gspread

st.set_page_config(page_title="Pickleball Generator", page_icon="🏓")

st.title("🏓 Pickleball Match Generator")
st.write("Generate balanced match schedules directly from your Spond export.")

# --- DATABASE SETUP (GOOGLE SHEETS) ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1o_T1bQ4qoyCok2mpFizODxt5llaoStjyGDHu9PMsd_I/edit"

@st.cache_resource
def get_gsheet_client():
    creds_dict = json.loads(st.secrets["gcp_service_account"])
    return gspread.service_account_from_dict(creds_dict)

gc = get_gsheet_client()
sheet = gc.open_by_url(SHEET_URL).sheet1

def load_db():
    # Read the data from Google Sheets expecting 3 columns now
    records = sheet.get_all_records()
    db = {}
    for row in records:
        # Check that the new column headers exist
        if 'First Name' in row and 'Last Name' in row and 'Gender' in row:
            first = str(row['First Name']).strip()
            last = str(row['Last Name']).strip()
            
            # Combine them for matching against the Spond text box
            full_name = f"{first} {last}".strip()
            
            if full_name: # Skip empty rows
                db[full_name] = str(row['Gender']).strip().upper()
    return db

def save_new_players(new_players_dict):
    rows_to_add = []
    for full_name, gender in new_players_dict.items():
        # Split the full name into First and Last at the first space
        parts = full_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        
        # Append as [First Name, Last Name, Gender]
        rows_to_add.append([first_name, last_name, gender])
        
    sheet.append_rows(rows_to_add)

# Load the player database from Google Sheets
player_db = load_db()

# --- UI: Inputs ---
st.sidebar.header("Settings")
courts_available = st.sidebar.slider("Courts Available", 1, 8, 3) 
num_rounds = st.sidebar.slider("Number of Rounds to Generate", 1, 10, 6)

st.write("### Player List")
st.write("Paste your players below (Just their names, one per line).")

default_players = """John Smith
Dave Jones
Mike Williams
Tom Brown
Steve Taylor
Chris Davies
Sarah Evans
Emma Wilson
Jane Thomas
Lucy Roberts
Anna Johnson
Chloe White"""

player_input = st.text_area("Spond Export", default_players, height=200)

# Extract names and clean up whitespace
input_names = [name.strip() for name in player_input.split('\n') if name.strip()]

# --- DATABASE CHECK ---
unknown_players = [name for name in input_names if name not in player_db]

if unknown_players:
    st.warning(f"⚠️ {len(unknown_players)} new player(s) detected! Please assign their gender below to save them to your Google Sheet.")
    
    with st.form("new_players_form"):
        new_genders = {}
        for name in unknown_players:
            new_genders[name] = st.radio(f"Gender for {name}", ["M", "F"], horizontal=True, key=f"gender_{name}")
        
        if st.form_submit_button("Save to Database"):
            with st.spinner("Saving to Google Sheets..."):
                save_new_players(new_genders)
            st.success("Players saved! Refreshing...")
            st.rerun() 

else:
    # --- CORE ENGINE ---
    def generate_schedule(players_list, num_courts, num_rounds):
        players = [{'name': name, 'gender': player_db[name]} for name in players_list]
        
        sit_outs = {p['name']: 0 for p in players}
        partner_history = {p['name']: set() for p in players}
        
        schedule = []
        max_playing_spots = num_courts * 4

        for round_num in range(1, num_rounds + 1):
            random.shuffle(players) 
            players.sort(key=lambda x: sit_outs[x['name']], reverse=True)
            
            active_players = players[:max_playing_spots]
            sitting_out = players[max_playing_spots:]
            
            for p in sitting_out:
                sit_outs[p['name']] += 1
                
            pairs = []
            successful_pairing = False
            
            for _ in range(50):
                temp_active = active_players[:]
                random.shuffle(temp_active)
                temp_pairs = []
                
                while temp_active:
                    p1 = temp_active.pop(0)
                    best_partner_idx = -1
                    
                    for i, p2 in enumerate(temp_active):
                        if p2['name'] not in partner_history[p1['name']]:
                            if p1['gender'] != p2['gender']:
                                best_partner_idx = i
                                break 
                            elif best_partner_idx == -1:
                                best_partner_idx = i 
                    
                    if best_partner_idx != -1:
                        p2 = temp_active.pop(best_partner_idx)
                        temp_pairs.append((p1, p2))
                    else:
                        break 
                
                if len(temp_pairs) == len(active_players) // 2:
                    pairs = temp_pairs
                    successful_pairing = True
                    break
                    
            if not successful_pairing:
                pairs = []
                temp_active = active_players[:]
                random.shuffle(temp_active)
                while temp_active:
                    p1 = temp_active.pop(0)
                    p2 = temp_active.pop(0)
                    pairs.append((p1, p2))

            for p1, p2 in pairs:
                partner_history[p1['name']].add(p2['name'])
                partner_history[p2['name']].add(p1['name'])
                
            round_matches = []
            for i in range(0, len(pairs), 2):
                if i + 1 < len(pairs):
                    round_matches.append((pairs[i], pairs[i+1]))
                    
            schedule.append({
                'round': round_num,
                'matches': round_matches,
                'sitting_out': [p['name'] for p in sitting_out]
            })
            
        return schedule, sit_outs

    # --- UI: Output ---
    if st.button("Generate Matches", type="primary"):
        if len(input_names) < 4:
            st.error("You need at least 4 players to generate a match!")
        else:
            with st.spinner('Calculating best matchups...'):
                schedule, final_sit_outs = generate_schedule(input_names, courts_available, num_rounds)
                
                st.success("Matches Generated!")
                
                for r in schedule:
                    st.write(f"### Round {r['round']}")
                    
                    if r['sitting_out']:
                        st.info(f"**Sitting out:** {', '.join(r['sitting_out'])}")
                    
                    for idx, match in enumerate(r['matches']):
                        t1_p1, t1_p2 = match[0]
                        t2_p1, t2_p2 = match[1]
                        
                        st.write(f"**Court {idx + 1}:** {t1_p1['name']} & {t1_p2['name']} **VS** {t2_p1['name']} & {t2_p2['name']}")
                    
                    st.divider()
                
                st.write("### Audit: Total Sit-Outs Per Player")
                st.write("This ensures everyone gets equal playing time.")
                st.json(final_sit_outs)
