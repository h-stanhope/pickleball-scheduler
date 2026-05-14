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

# --- TEXT NORMALIZER ---
def normalize_name(name):
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    return name.strip().lower()

player_db = load_db()
db_names = sorted(list(player_db.keys()))
normalized_db = {normalize_name(name): name for name in db_names}

# --- UI: Inputs ---
st.sidebar.header("Session Settings")
courts_available = st.sidebar.slider("Courts Available", 1, 8, 3) 

# NEW: Dynamic Time Settings
session_start = st.sidebar.time_input("Session Start Time", value=time(19, 0))
session_length_hours = st.sidebar.number_input("Length of Session (Hours)", min_value=1.0, max_value=5.0, value=2.0, step=0.5)
include_warmup = st.sidebar.checkbox("Include 5-min Warmup?", value=True)

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
    # --- CORE ENGINE (Monte Carlo Scoring Algorithm) ---
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
                # BUG FIX APPLIED: reverse=True ensures fair sit-outs
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
            with st.spinner('Calculating optimal timings & running 1000 simulations...'):
                
                # --- TIME & ROUND CALCULATOR ---
                max_playing_spots = min(courts_available * 4, (total_players // 4) * 4)
                sitting_out_per_round = total_players - max_playing_spots
                
                total_time_mins = int(session_length_hours * 60)
                usable_time = total_time_mins - 2 # Reserve 2 mins for clearup
                if include_warmup:
                    usable_time -= 5
                
                best_r = 0
                best_d = 0
                best_scoring_combo = (-1, -1, -1) # (is_perfect_mod, rounds, duration)
                
                # Test all possible round lengths between 12 and 15 mins
                for d in range(12, 16):
                    r = (usable_time + 1) // (d + 1) # +1 accounts for the fact there's no changeover after the last round
                    if r > 0:
                        total_sitouts = r * sitting_out_per_round
                        # We want the sitouts to divide perfectly into the total players
                        is_perfect = 1 if (sitting_out_per_round > 0 and total_sitouts % total_players == 0) else 0
                        if sitting_out_per_round == 0:
                            is_perfect = 1 # Always perfect if no one sits out
                        
                        score = (is_perfect, r, d)
                        if score > best_scoring_combo:
                            best_scoring_combo = score
                            best_r = r
                            best_d = d
                
                if best_r == 0:
                    st.error("The session is too short to fit even a single 12-minute round. Please extend the session length.")
                else:
                    # Run the engine with the perfectly calculated rounds
                    schedule, final_sit_outs = generate_schedule(final_input_names, courts_available, best_r)
                    
                    st.success("Matches Generated!")
                    
                    # --- SMART OVERVIEW METRICS ---
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("👥 Players", total_players)
                    col2.metric("🔄 Rounds", best_r)
                    col3.metric("⏱️ Match Time", f"{best_d} min")
                    col4.metric("🏸 Courts Used", max_playing_spots // 4)
                    
                    st.divider()
                    
                    # --- TIME RENDERING & WHATSAPP GENERATION ---
                    current_time = datetime.combine(datetime.today(), session_start)
                    session_end_time = current_time + timedelta(hours=session_length_hours)
                    
                    whatsapp_text = f"🏓 *Tonight's Pickleball Schedule* 🏓\n"
                    whatsapp_text += f"⏱️ *Session:* {current_time.strftime('%I:%M %p')} - {session_end_time.strftime('%I:%M %p')}\n"
                    whatsapp_text += f"👥 *Players:* {total_players} | 🏸 *Courts:* {max_playing_spots // 4}\n"
                    whatsapp_text += f"⏱️ *Match Time:* {best_d} mins\n\n"
                    
                    if include_warmup:
                        warmup_end = current_time + timedelta(minutes=5)
                        st.info(f"🤸 **{current_time.strftime('%I:%M %p')} - {warmup_end.strftime('%I:%M %p')}**: Warmup")
                        whatsapp_text += f"🤸 *{current_time.strftime('%I:%M %p')} - {warmup_end.strftime('%I:%M %p')}*: Warmup\n\n"
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
                        
                        # Add 1 minute changeover
                        current_time = round_end + timedelta(minutes=1) 
                    
                    # Add Clearup at the end
                    st.warning(f"🧹 **{current_time.strftime('%I:%M %p')} - {session_end_time.strftime('%I:%M %p')}**: Clear up & Finish")
                    whatsapp_text += f"🧹 *{current_time.strftime('%I:%M %p')} - {session_end_time.strftime('%I:%M %p')}*: Clear up & Finish\n"
                    
                    st.write("### WhatsApp Export")
                    st.write("Click the copy button in the top right corner of the box below to paste this into your group chat!")
                    st.code(whatsapp_text, language="markdown")
                    
                    st.write("### Audit: Total Sit-Outs Per Player")
                    st.json(final_sit_outs)
