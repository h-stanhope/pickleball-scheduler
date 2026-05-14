import streamlit as st
import random
import json
import gspread
import unicodedata
import collections
from datetime import datetime, time, timedelta

st.set_page_config(page_title="Pickleball Generator", page_icon="🏓")

st.title("🏓 Pickleball Match Generator")
st.write("Generate balanced match schedules directly from your Google Sheets database.")

# --- DATABASE SETUP (GOOGLE SHEETS) ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1OqunrQlJmNGdMjePYtQgK0jVfDZ76bISP8HCu5pepMo/edit"

@st.cache_resource
def get_gsheet_client():
    creds_dict = json.loads(st.secrets["gcp_service_account"])
    return gspread.service_account_from_dict(creds_dict)

gc = get_gsheet_client()
sheet = gc.open_by_url(SHEET_URL).sheet1

def load_db():
    records = sheet.get_all_records()
    db = {}
    for row in records:
        if 'First Name' in row and 'Last Name' in row and 'Gender' in row:
            first = str(row['First Name']).strip()
            last = str(row['Last Name']).strip()
            full_name = f"{first} {last}".strip()
            if full_name: 
                db[full_name] = str(row['Gender']).strip().upper()
    return db

def save_new_players(new_players_dict):
    rows_to_add = []
    for full_name, gender in new_players_dict.items():
        parts = full_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        rows_to_add.append([first_name, last_name, gender])
    sheet.append_rows(rows_to_add)

def normalize_name(name):
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    return name.strip().lower()

player_db = load_db()
db_names = sorted(list(player_db.keys()))
normalized_db = {normalize_name(name): name for name in db_names}

# --- UI: Inputs ---
st.sidebar.header("Session Settings")
courts_available = st.sidebar.slider("Courts Available", 1, 8, 3) 

session_start = st.sidebar.time_input("Session Start Time", value=time(19, 0))

# Custom 15-minute increment dropdown for Session Length
session_length_options = []
for h in range(1, 6):
    for m in [0, 15, 30, 45]:
        if h == 5 and m > 0: continue 
        parts = []
        if h == 1: parts.append("1 hour")
        elif h > 1: parts.append(f"{h} hours")
        if m > 0: parts.append(f"{m} mins")
        session_length_options.append({"label": " ".join(parts), "mins": h * 60 + m})

default_index = next((i for i, item in enumerate(session_length_options) if item["mins"] == 120), 0)
selected_session = st.sidebar.selectbox(
    "Length of Session", 
    options=[opt["label"] for opt in session_length_options],
    index=default_index
)
total_time_mins = next(opt["mins"] for opt in session_length_options if opt["label"] == selected_session)

include_warmup = st.sidebar.checkbox("Include Warmup", value=True)

st.write("### Attending Players")

selected_db_players = st.multiselect(
    "Select members from your database:", 
    options=db_names,
    help="Click and type to quickly search for members."
)

st.write("---")
new_players_text = st.text_area(
    "Brand new players? (Not in database)", 
    placeholder="Type new names here, one per line...", 
    height=100
)

final_input_names = selected_db_players.copy()
raw_new_names = [name.strip() for name in new_players_text.split('\n') if name.strip()]

unknown_players = []

for raw_name in raw_new_names:
    norm_name = normalize_name(raw_name)
    if norm_name in normalized_db:
        correct_db_name = normalized_db[norm_name]
        if correct_db_name not in final_input_names:
            final_input_names.append(correct_db_name)
    else:
        unknown_players.append(raw_name)
        final_input_names.append(raw_name)

# --- DATABASE CHECK ---
if unknown_players:
    st.warning(f"⚠️ {len(unknown_players)} new player(s) detected! Please assign their gender below.")
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
    def generate_schedule(players_list, num_courts, num_rounds):
        players = [{'name': name, 'gender': player_db[name]} for name in players_list]
        
        total_f = sum(1 for p in players if p['gender'] == 'F')
        total_m = sum(1 for p in players if p['gender'] == 'M')
        
        req_f_matches = 2 if total_f >= 6 else (1 if total_f >= 4 else 0)
        req_m_matches = 2 if total_m >= 6 else (1 if total_m >= 4 else 0)

        best_schedule = None
        best_score = -float('inf')
        best_sit_outs = None
        
        max_playing = min(num_courts * 4, (len(players) // 4) * 4)

        for _ in range(1000):
            sit_outs = {p['name']: 0 for p in players}
            partner_history = {p['name']: set() for p in players}
            schedule = []

            for round_num in range(1, num_rounds + 1):
                temp_players = players[:]
                random.shuffle(temp_players)
                temp_players.sort(key=lambda x: sit_outs[x['name']], reverse=True)
                
                active_players = temp_players[:max_playing]
                sitting_out = temp_players[max_playing:]
                
                for p in sitting_out:
                    sit_outs[p['name']] += 1
                    
                m_active = [p for p in active_players if p['gender'] == 'M']
                f_active = [p for p in active_players if p['gender'] == 'F']
                random.shuffle(m_active)
                random.shuffle(f_active)

                courts = []
                while len(m_active) + len(f_active) >= 4:
                    options = []
                    if len(m_active) >= 2 and len(f_active) >= 2: options.append('mixed')
                    if len(m_active) >= 4: options.append('all_m')
                    if len(f_active) >= 4: options.append('all_f')

                    if options:
                        choice = random.choice(options)
                        if choice == 'mixed':
                            court = [m_active.pop(), m_active.pop(), f_active.pop(), f_active.pop()]
                        elif choice == 'all_m':
                            court = [m_active.pop(), m_active.pop(), m_active.pop(), m_active.pop()]
                        elif choice == 'all_f':
                            court = [f_active.pop(), f_active.pop(), f_active.pop(), f_active.pop()]
                    else:
                        court = []
                        for _ in range(4):
                            if m_active and f_active:
                                court.append(m_active.pop() if random.random() > 0.5 else f_active.pop())
                            elif m_active:
                                court.append(m_active.pop())
                            elif f_active:
                                court.append(f_active.pop())
                    courts.append(court)

                round_matches = []
                for court in courts:
                    p1, p2, p3, p4 = court
                    ways = [((p1, p2), (p3, p4)), ((p1, p3), (p2, p4)), ((p1, p4), (p2, p3))]
                    best_way = ways[0]
                    best_w_score = -999

                    for way in ways:
                        t1, t2 = way
                        w_score = 0
                        if t1[1]['name'] in partner_history[t1[0]['name']]: w_score -= 100
                        if t2[1]['name'] in partner_history[t2[0]['name']]: w_score -= 100

                        g1 = sorted([t1[0]['gender'], t1[1]['gender']])
                        g2 = sorted([t2[0]['gender'], t2[1]['gender']])

                        if g1 == ['F', 'M'] and g2 == ['F', 'M']: w_score += 10
                        elif g1 == ['M', 'M'] and g2 == ['M', 'M']: w_score += 10
                        elif g1 == ['F', 'F'] and g2 == ['F', 'F']: w_score += 10

                        if w_score > best_w_score:
                            best_w_score = w_score
                            best_way = way

                    t1, t2 = best_way
                    partner_history[t1[0]['name']].add(t1[1]['name'])
                    partner_history[t1[1]['name']].add(t1[0]['name'])
                    partner_history[t2[0]['name']].add(t2[1]['name'])
                    partner_history[t2[1]['name']].add(t2[0]['name'])
                    round_matches.append(best_way)

                schedule.append({
                    'round': round_num,
                    'matches': round_matches,
                    'sitting_out': [p['name'] for p in sitting_out]
                })

            score = 0
            match_types = {'all_M': 0, 'all_F': 0, 'mixed': 0, 'awkward': 0}
            partner_counts = collections.defaultdict(int)

            for r in schedule:
                for match in r['matches']:
                    t1_p1, t1_p2 = match[0]
                    t2_p1, t2_p2 = match[1]

                    partner_counts[frozenset([t1_p1['name'], t1_p2['name']])] += 1
                    partner_counts[frozenset([t2_p1['name'], t2_p2['name']])] += 1

                    m_count = sum(1 for p in [t1_p1, t1_p2, t2_p1, t2_p2] if p['gender'] == 'M')
                    if m_count == 4: match_types['all_M'] += 1
                    elif m_count == 0: match_types['all_F'] += 1
                    elif m_count == 2: match_types['mixed'] += 1
                    else: match_types['awkward'] += 1

            for pair, count in partner_counts.items():
                if count > 1: score -= (count - 1) * 500

            score -= match_types['awkward'] * 1000
            
            if match_types['all_F'] < req_f_matches:
                score -= (req_f_matches - match_types['all_F']) * 800
            if match_types['all_M'] < req_m_matches:
                score -= (req_m_matches - match_types['all_M']) * 800

            score += match_types['mixed'] * 10
            score += match_types['all_F'] * 10
            score += match_types['all_M'] * 10

            if score > best_score:
                best_score = score
                best_schedule = schedule
                best_sit_outs = sit_outs

        return best_schedule, best_sit_outs

    # --- UI: Output ---
    if st.button("Generate Matches", type="primary"):
        total_players = len(final_input_names)
        if total_players < 4:
            st.error("You need at least 4 players to generate a match!")
        else:
            with st.spinner('Calculating optimal timings & running simulations...'):
                
                max_playing_spots = min(courts_available * 4, (total_players // 4) * 4)
                
                best_r = 0
                best_d = 0
                best_warmup = 0
                best_clearup = 0
                best_score = (-1, -1) # (Total Match Time, -Clearup Time)

                # --- NEW OPTIMIZER: Maximize playing time ---
                for d in range(12, 16):
                    # Minimum non-playing time: 7 mins if warmup, 2 mins if no warmup
                    min_non_playing = 7 if include_warmup else 2
                    available_for_matches = total_time_mins - min_non_playing
                    
                    # Calculate MAX rounds possible for this duration
                    r = (available_for_matches + 1) // (d + 1)
                    
                    if r > 0:
                        time_for_matches = (r * d) + (r - 1)
                        remaining_time = total_time_mins - time_for_matches
                        
                        if include_warmup:
                            # Warmup flexes between 5 and 10 to eat up spare time, leaving 2+ for clearup
                            warmup = min(10, remaining_time - 2)
                            clearup = remaining_time - warmup
                        else:
                            warmup = 0
                            clearup = remaining_time
                            
                        total_play_time = r * d
                        
                        # Score ranks the absolute most time spent playing first, shortest clearup second
                        score = (total_play_time, -clearup)
                        
                        if score > best_score:
                            best_score = score
                            best_r = r
                            best_d = d
                            best_warmup = warmup
                            best_clearup = clearup
                
                if best_r == 0:
                    st.error("The session is too short to fit the matches properly. Please extend the session length.")
                else:
                    schedule, final_sit_outs = generate_schedule(final_input_names, courts_available, best_r)
                    
                    st.success("Matches Generated!")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("👥 Players", total_players)
                    col2.metric("🔄 Rounds", best_r)
                    col3.metric("⏱️ Match Time", f"{best_d} min")
                    col4.metric("🏸 Courts Used", max_playing_spots // 4)
                    
                    st.divider()
                    
                    current_time = datetime.combine(datetime.today(), session_start)
                    session_end_time = current_time + timedelta(minutes=total_time_mins)
                    
                    whatsapp_text = f"🏓 *Tonight's Pickleball Schedule* 🏓\n"
                    whatsapp_text += f"⏱️ *Session:* {current_time.strftime('%I:%M %p')} - {session_end_time.strftime('%I:%M %p')}\n"
                    whatsapp_text += f"👥 *Players:* {total_players} | 🏸 *Courts:* {max_playing_spots // 4}\n"
                    whatsapp_text += f"⏱️ *Match Time:* {best_d} mins\n\n"
                    
                    if include_warmup:
                        warmup_end = current_time + timedelta(minutes=best_warmup)
                        st.info(f"🤸 **{current_time.strftime('%I:%M %p')} - {warmup_end.strftime('%I:%M %p')}**: Warmup ({best_warmup} mins)")
                        whatsapp_text += f"🤸 *{current_time.strftime('%I:%M %p')} - {warmup_end.strftime('%I:%M %p')}*: Warmup ({best_warmup} mins)\n\n"
                        current_time = warmup_end
                    
                    for r in schedule:
                        round_start = current_time
                        round_end = current_time + timedelta(minutes=best_d)
                        
                        st.write(f"### Round {r['round']} ({round_start.strftime('%I:%M %p')} - {round_end.strftime('%I:%M %p')})")
                        whatsapp_text += f"🟢 *ROUND {r['round']}* ({round_start.strftime('%I:%M %p')} - {round_end.strftime('%I:%M %p')})\n"
                        
                        if r['sitting_out']:
                            st.info(f"**Sitting out:** {', '.join(r['sitting_out'])}")
                            whatsapp_text += f"🛋️ *Sitting out:* {', '.join(r['sitting_out'])}\n"
                        
                        for idx, match in enumerate(r['matches']):
                            t1_p1, t1_p2 = match[0]
                            t2_p1, t2_p2 = match[1]
                            
                            match_str = f"{t1_p1['name']} & {t1_p2['name']} VS {t2_p1['name']} & {t2_p2['name']}"
                            st.write(f"**Court {idx + 1}:** {match_str}")
                            whatsapp_text += f"🏸 Court {idx + 1}: {match_str}\n"
                        
                        st.divider()
                        whatsapp_text += "\n"
                        
                        current_time = round_end + timedelta(minutes=1) 
                    
                    st.warning(f"🧹 **{current_time.strftime('%I:%M %p')} - {session_end_time.strftime('%I:%M %p')}**: Clear up & Finish ({best_clearup} mins)")
                    whatsapp_text += f"🧹 *{current_time.strftime('%I:%M %p')} - {session_end_time.strftime('%I:%M %p')}*: Clear up & Finish ({best_clearup} mins)\n"
                    
                    st.write("### WhatsApp Export")
                    st.write("Click the copy button in the top right corner of the box below to paste this into your group chat!")
                    st.code(whatsapp_text, language="markdown")
                    
                    st.write("### Audit: Total Sit-Outs Per Player")
                    st.json(final_sit_outs)
