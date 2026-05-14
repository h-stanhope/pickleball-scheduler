import streamlit as st
import random

st.set_page_config(page_title="Pickleball Generator", page_icon="🏓")

st.title("🏓 Pickleball Match Generator")
st.write("Generate balanced match schedules directly from your Spond export.")

# --- UI: Inputs ---
st.sidebar.header("Settings")
courts_available = st.sidebar.slider("Courts Available", 1, 3, 3)
num_rounds = st.sidebar.slider("Number of Rounds to Generate", 1, 10, 6)

st.write("### Player List")
st.write("Paste your players below. Format: `Name, Gender` (e.g., John, M or Jane, F)")

default_players = """John, M
Dave, M
Mike, M
Tom, M
Steve, M
Chris, M
Sarah, F
Emma, F
Jane, F
Lucy, F
Anna, F
Chloe, F"""

player_input = st.text_area("Spond Export", default_players, height=200)

# --- CORE ENGINE ---
def parse_players(input_text):
    players = []
    lines = input_text.strip().split('\n')
    for line in lines:
        if ',' in line:
            name, gender = line.split(',', 1)
            players.append({'name': name.strip(), 'gender': gender.strip().upper()})
    return players

def generate_schedule(players, num_courts, num_rounds):
    # Initialize Tracking Memory
    sit_outs = {p['name']: 0 for p in players}
    partner_history = {p['name']: set() for p in players}
    
    schedule = []
    
    max_playing_spots = num_courts * 4

    for round_num in range(1, num_rounds + 1):
        # 1. Determine Sit-Outs
        # Shuffle first so ties in sit_outs are broken randomly
        random.shuffle(players) 
        players.sort(key=lambda x: sit_outs[x['name']])
        
        active_players = players[:max_playing_spots]
        sitting_out = players[max_playing_spots:]
        
        for p in sitting_out:
            sit_outs[p['name']] += 1
            
        # 2. Form Pairs (Randomized Greedy Approach)
        pairs = []
        successful_pairing = False
        
        # Try up to 50 times to find a perfect combination
        for _ in range(50):
            temp_active = active_players[:]
            random.shuffle(temp_active)
            temp_pairs = []
            
            while temp_active:
                p1 = temp_active.pop(0)
                best_partner_idx = -1
                
                # Look for a valid partner
                for i, p2 in enumerate(temp_active):
                    if p2['name'] not in partner_history[p1['name']]:
                        # Prefer Mixed if possible
                        if p1['gender'] != p2['gender']:
                            best_partner_idx = i
                            break # Found perfect mixed match
                        elif best_partner_idx == -1:
                            best_partner_idx = i # Save same-gender match as backup
                
                if best_partner_idx != -1:
                    p2 = temp_active.pop(best_partner_idx)
                    temp_pairs.append((p1, p2))
                else:
                    # Failed to find a valid partner for p1, break and retry
                    break 
            
            if len(temp_pairs) == len(active_players) // 2:
                pairs = temp_pairs
                successful_pairing = True
                break
                
        # The Fail-safe: If we couldn't find perfect pairs, relax the rules and force it.
        if not successful_pairing:
            pairs = []
            temp_active = active_players[:]
            random.shuffle(temp_active)
            while temp_active:
                p1 = temp_active.pop(0)
                p2 = temp_active.pop(0)
                pairs.append((p1, p2))

        # Update partner history memory
        for p1, p2 in pairs:
            partner_history[p1['name']].add(p2['name'])
            partner_history[p2['name']].add(p1['name'])
            
        # 3. Match Pairs to Courts
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
    players = parse_players(player_input)
    
    if len(players) < 4:
        st.error("You need at least 4 players to generate a match!")
    else:
        with st.spinner('Calculating best matchups...'):
            schedule, final_sit_outs = generate_schedule(players, courts_available, num_rounds)
            
            st.success("Matches Generated!")
            
            # Display Schedule
            for r in schedule:
                st.write(f"### Round {r['round']}")
                
                if r['sitting_out']:
                    st.info(f"**Sitting out:** {', '.join(r['sitting_out'])}")
                
                # Format Matches
                for idx, match in enumerate(r['matches']):
                    t1_p1, t1_p2 = match[0]
                    t2_p1, t2_p2 = match[1]
                    
                    st.write(f"**Court {idx + 1}:** {t1_p1['name']} ({t1_p1['gender']}) & {t1_p2['name']} ({t1_p2['gender']}) **VS** {t2_p1['name']} ({t2_p1['gender']}) & {t2_p2['name']} ({t2_p2['gender']})")
                
                st.divider()
            
            # Display Sit-Out Audit
            st.write("### Audit: Total Sit-Outs Per Player")
            st.write("This ensures everyone gets equal playing time.")
            st.json(final_sit_outs)