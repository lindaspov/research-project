from flask import Flask, render_template, request, redirect, jsonify, session, send_file
import random
import time
import csv
import os
from datetime import datetime
from threading import Lock

app = Flask(__name__)
app.secret_key = "supersecretkey123"

ACCESS_CODE = "auction2026"

player_lock = Lock()
active_players = []

# ===============================
# DATA LOGGING
# ===============================

DATA_FILE = None
ROUND_FILE = None

def initialize_logging():

    global DATA_FILE, ROUND_FILE

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    DATA_FILE = f"auction_data_{timestamp}.csv"
    ROUND_FILE = f"round_results_{timestamp}.csv"
    
    auction_state["auction_data_file"] = DATA_FILE
    auction_state["round_results_file"] = ROUND_FILE

    with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "time",
            "round",
            "player",
            "strategy",
            "cost",
            "bid",
            "margin",
            "cumulative_profit",
        ])

    with open(ROUND_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "round",
            "player",
            "winner",
            "strategy",
            "cost",
            "profit",
            "bonus",
            "winning_bid",
            "total_profit"
        ])

def log_bid(player, amount):
    real_name = auction_state.get("usernames", {}).get(player, player)

    cost = auction_state["participant_costs"].get(player)
    margin = amount - cost if cost is not None else 0

    cumulative_profit = auction_state["total_profits"].get(player, 0)

    if player in HUMAN_PLAYERS:
        round_index = auction_state["round"] - 1
        matchup = auction_state.get("round_matchups")
        
        if matchup:
            pair = matchup[round_index]
            if player == "Player A":
                strategy = strategies[pair[0]]["title"]
            else:
                strategy = strategies[pair[1]]["title"]
        else:
            strategy = ""
    else:
        strategy = ""

    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:

        writer = csv.writer(f, delimiter=";")

        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            auction_state["round"],
            real_name,
            strategy,
            cost,
            amount,
            margin,
            cumulative_profit,
            "", #round_winner (kommt später)
            "", #overall_winner
            ""  #bonus
        ])

        f.flush()
        os.fsync(f.fileno())

# ===============================
# STRATEGY TEXTS (UNCHANGED)
# ===============================

strategies = {
    "incremental": {
        "title": "Incremental Bidding",
        "text": """You adapt gradually – reducing your price in small, controlled steps.

How to proceed:
1. Begin with a moderate bid.
2. Observe the lowest current bids.
3. Each time you are undercut, lower your price slightly (e.g., by 2–5 €).
4. Keep a buffer and avoid major price drops.

Key points:
- You respond – but never overreact.
- Focus on precision and control, not speed.
- Always consider whether your next bid keeps you profitable.
"""
    },
    "aggressive": {
        "title": "Aggressive Flooding",
        "text": """You aim to dominate the auction by being constantly present and applying pressure.

How to proceed:
1. Submit bids frequently – never stay silent for too long.
2. React immediately whenever someone underbids you.
3. Keep the bidding tempo high and maintain visibility.

Key points:
- Intimidate others by being hyperactive.
- You don’t need the lowest price – just make others feel they can’t keep up.
- Keep track of your profit margin while staying aggressive.
"""
    },
    "early": {
        "title": "Early Signal",
        "text": """Your goal is to dominate the auction by being the first and boldest.

How to proceed:
1. Submit a very aggressive bid at the very beginning – well below the expected average.
2. Avoid bidding again – let your opening move signal dominance.

Key points:
- Use surprise to your advantage.
- Many competitors hesitate if they see strong early pressure.
- Make sure your bid still leaves enough margin to stay profitable.
"""
    },
    "bottom": {
        "title": "Bottom-Line Discipline",
        "text": """Your priority is financial control – no risks, no losses.

How to proceed:
1. Define your minimum acceptable price.
2. Do not submit any bid below this bottom line.

Key points:
- Walking away is better than accepting a loss-making contract.
- Stay committed to long-term profitability.
- Ignore emotional reactions.
"""
    },
    "sniping": {
        "title": "Sniping",
        "text": """Your strength lies in timing – act only at the last possible moment.

How to proceed:
1. Observe quietly throughout the round.
2. Submit your bid only in the final seconds.
3. Slightly undercut the lowest current bid.

Key points:
- Early bidding exposes your tactics.
- Timing is everything.
- Even a last-minute bid must protect your profit margin.
"""
    }
}

# ===============================
# CONSTANTS
# ===============================

START_PRICE = 200000
AUCTION_DURATION = 120

# ===============================
# PLAYERS
# ===============================

HUMAN_PLAYERS = ["Player A", "Player B"]
DUMMY_PLAYERS = ["Sarah", "Noah", "Jenny"]
ALL_PLAYERS = HUMAN_PLAYERS + DUMMY_PLAYERS

# ===============================
# AUCTION STATE
# ===============================

auction_state = {
    "round": 1,
    "max_rounds": 25,
    "active": False,
    "start_time": None,
    "lowest_bid": None,
    "lowest_bidder": None,
    "bids": [],
    "last_bid_by_player": {},
    "participant_costs": {},
    "profits": {},
    "bonuses": {},
    "total_profits": {},
    "cumulative_profit": {},
    "total_bonuses": {},
    "strategy": None,
    "strategy_sequence": [],
    "round_finished": False,
    "human_slots": [],
    "last_actions": {
        "Sarah": 0,
        "Noah": 0,
        "Jenny": 0
    }
}

# ===============================
# CONFIRMATION SYSTEM
# ===============================

confirmations = {
    "Player A": False,
    "Player B": False
}

def reset_confirmations():
    confirmations["Player A"] = False
    confirmations["Player B"] = False
    
    auction_state["human_slots"] = []

# ===============================
# STRATEGY RANDOMIZATION
# ===============================

def generate_balanced_rounds():
    import itertools
    import random

    strategies_list = list(strategies.keys())

    rounds = list(itertools.product(strategies_list, strategies_list))

    random.shuffle(rounds)

    return rounds

# ===============================
# ROUTES
# ===============================

@app.route("/", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        code = request.form.get("code")

        if code == ACCESS_CODE:
            session["authorized"] = True
            return redirect("/welcome")
        else:
            error = "Wrong access code ❌"

    return render_template("login.html", error=error)

@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

@app.route("/name", methods=["GET", "POST"])
def name():
    if request.method == "POST":
        username = request.form["player_name"]
        gender = request.form["gender"]   # 👈 NEU

        with player_lock:
            # Session zurücksetzen falls Player nicht mehr aktiv
            existing = session.get("player")
            if existing and existing not in active_players:
                session.pop("player", None)

            if "player" not in session:
                if len(active_players) == 0:
                    session["player"] = "Player A"
                    active_players.append("Player A")
                elif len(active_players) == 1:
                    session["player"] = "Player B"
                    active_players.append("Player B")
                else:
                    return "Experiment voll – bitte warten.", 403

        # 🟢 USERNAMES speichern
        if "usernames" not in auction_state:
            auction_state["usernames"] = {}

        auction_state["usernames"][session["player"]] = username

        # 🟢 GENDER speichern (NEU)
        if "genders" not in auction_state:
            auction_state["genders"] = {}

        auction_state["genders"][session["player"]] = gender

        # 🟢 Optional auch in Session speichern
        session["gender"] = gender

        # 🟢 Matchups initialisieren (wie vorher)
        if "round_matchups" not in auction_state or not auction_state["round_matchups"]:
            auction_state["round_matchups"] = generate_balanced_rounds()

        return redirect("/scenario")

    return render_template("name.html")

@app.route("/scenario")
def scenario():
    player = session.get("player")
    return render_template("scenario.html", player=player)

@app.route("/strategy")
def strategy():

    if auction_state["active"]:
        return redirect("/auction")

    round_index = auction_state["round"] - 1
    pair = auction_state["round_matchups"][round_index]

    player = session.get("player")
    
    if player not in ["Player A", "Player B"]:
        return redirect("/name")
    
    if player not in ["Player A", "Player B"]:
        return redirect("/name")

    if player == "Player A":
        chosen_key = pair[0]
    else:
        chosen_key = pair[1]

    strategy = strategies[chosen_key]

    return render_template(
        "strategy.html",
        title=strategy["title"],
        text=strategy["text"]
    )
    
@app.route("/auction")
def auction():
    
    if not session.get("authorized"):
        return redirect("/")

    player = session.get("player")

    if player not in ["Player A", "Player B"]:
        return redirect("/name")

    #AUKTION STARTEN (WICHTIG!)
    if not auction_state["active"]:
        start_round()
        
    if "round_matchups" not in auction_state:
        auction_state["round_matchups"] = generate_balanced_rounds()

    round_index = auction_state["round"] - 1
    pair = auction_state["round_matchups"][round_index]

    if player == "Player A":
        chosen_key = pair[0]
    else:
        chosen_key = pair[1]

    strategy = strategies[chosen_key]

    return render_template(
        "auction.html",
        round=auction_state["round"],
        max_rounds=auction_state["max_rounds"],
        strategy=strategy,
        last_bid=auction_state["last_bid_by_player"].get(player),
        username=session.get("username")
    )

@app.route("/leaderboard")
def leaderboard():
    
    if not session.get("authorized"):
        return redirect("/")

    current_round = auction_state["round"]

    # 🔵 jede 5. Runde → kumuliert
    if current_round % 5 == 0:
        profits = auction_state["total_profits"]
        bonuses = auction_state["total_bonuses"]
    else:
        # 🟢 sonst → nur aktuelle Runde
        profits = auction_state["profits"]
        bonuses = auction_state["bonuses"]

    #Sortierung
    sorted_players = sorted(
        ALL_PLAYERS,
        key=lambda p: profits.get(p, 0),
        reverse=True
    )

    #Persönliche Nachricht
    import random
    current_player = session.get("player")

    loser_messages = [
        "Aw, you lost! Try harder next round 💪",
        "Close one! Maybe next time 👀",
        "Not your round… but don't give up!",
        "Ouch… that didn’t go as planned 😬",
        "Not quite enough — but very close 👌",
        "Margins matter. Stay sharp for the next round ⚡",
        "You were in the game — just not on top this time 🔥",
        "Not your round — but the next one might be 🔄",
        "Aw, tough round. Shake it off and try again 💪",
        "Stay focused — you're not far off 🎯",
        "You tried. That’s something… I guess 😬",
        "That didn’t age well 😬",
        "Not gonna lie — that was rough 😬",
        "That one hurt. A lot. 💀",
        "The market was tough this time 📉"
    ]

    player_message = ""

    if current_player:
        if current_player == sorted_players[0]:
            player_message = "🏆 You won this round!"
        else:
            player_message = random.choice(loser_messages)

    # Template rendern
    return render_template(
        "leaderboard.html",
        round=auction_state["round"],
        max_rounds=auction_state["max_rounds"],
        leaderboard=sorted_players,
        profits=profits,
        bonuses=bonuses,
        usernames=auction_state.get("usernames", {}),
        player_message=player_message
    )

@app.route("/download_results")
def download_results():
    file = auction_state.get("round_results_file")
    if not file:
        return "No results file yet", 404
    return send_file(file, as_attachment=True)


@app.route("/download_data")
def download_data():
    file = auction_state.get("auction_data_file")
    if not file:
        return "No data file yet", 404
    return send_file(file, as_attachment=True)


@app.route("/next_round", methods=["POST"])
def next_round():

    if not auction_state["round_finished"]:
        return redirect("/strategy")

    if auction_state["round"] < auction_state["max_rounds"]:
        auction_state["round"] += 1
        auction_state["round_finished"] = False
        reset_confirmations()

        return redirect("/strategy")

    return redirect("/goodbye")

# ===============================
# CONFIRMATION API
# ===============================

@app.route("/confirm_strategy", methods=["POST"])
def confirm_strategy():
    player = session.get("player")
    if player in confirmations:
        confirmations[player] = True
    confirmed_total = 3 + sum(confirmations.values())
    if confirmed_total == 5 and not auction_state["active"]:
        auction_state["active"] = True
        start_round()
    return jsonify({
        "confirmed": confirmed_total,
        "total": 5,
        "ready": confirmed_total == 5,
        "player": player
    })

@app.route("/confirmation_status")
def confirmation_status():

    confirmed_total = 3 + sum(confirmations.values())

    return jsonify({
        "confirmed": confirmed_total,
        "total": 5,
        "ready": confirmed_total == 5
    })

# ===============================
# API
# ===============================

@app.route("/status")
def status():

    # letzten Bid holen
    last = auction_state["bids"][-1] if auction_state["bids"] else None

    # echten Namen einsetzen (falls Spieler)
    player = request.args.get("player")

    if last:
        original_player = last["player"]
        name = auction_state.get("usernames", {}).get(original_player, original_player)

        last = last.copy()
        last["player"] = name
        last["is_self"] = (original_player == player)

    if not auction_state["active"]:
        return jsonify({
            "active": False,
            "remaining": 0,
            "lowest_bid": auction_state["lowest_bid"],
            "last_bid": last
        })

    elapsed = int(time.time() - auction_state["start_time"])
    remaining = max(0, AUCTION_DURATION - elapsed)

    if remaining > 0:
        process_dummies()

    if remaining <= 0 and auction_state["active"]:
        auction_state["active"] = False
        auction_state["round_finished"] = True
        calculate_results()

    player = session.get("player")
    
    return jsonify({
        "active": auction_state["active"],
        "remaining": remaining,
        "lowest_bid": auction_state["lowest_bid"],
        "last_bid": last,
        "your_last_bid": auction_state["last_bid_by_player"].get(player)
    })

@app.route("/bid", methods=["POST"])
def bid():

    if not auction_state["active"]:
        return jsonify({"success": False, "message": "Auction not active"})

    try:
        amount = int(request.form["amount"])
    except:
        return jsonify({"success": False, "message": "Invalid bid"})

    player = session.get("player")
    cost = auction_state["participant_costs"][player]

    # REGELN
    #if amount < cost:
    #return jsonify({"success": False, "message": "Bid below your production cost"})

    if auction_state["lowest_bid"] is None:
        if amount >= START_PRICE:
            return jsonify({"success": False, "message": "Bid must be below start price"})
    else:
        if amount >= auction_state["lowest_bid"]:
            return jsonify({
                "success": False,
                "message": "⚠ You have already been underbid. Please submit a lower bid."
            })

    register_bid(player, amount)

    return jsonify({"success": True})

# ===============================
# CORE LOGIC
# ===============================

def start_round():

    auction_state["active"] = True
    auction_state["start_time"] = time.time()

    auction_state["lowest_bid"] = None
    auction_state["lowest_bidder"] = None
    auction_state["bids"] = []
    
    auction_state["last_bid_by_player"] = {}

    auction_state["profits"] = {}
    auction_state["bonuses"] = {}

    auction_state["round_finished"] = False

    true_cost = random.randint(35000, 50000)

    auction_state["participant_costs"] = {
        p: true_cost
        for p in ALL_PLAYERS
    }

    for d in DUMMY_PLAYERS:
        auction_state["last_actions"][d] = time.time()

def register_bid(player, amount):

    auction_state["lowest_bid"] = amount
    auction_state["lowest_bidder"] = player

    auction_state["bids"].append({
        "player": player,
        "amount": amount
    })

    auction_state["last_bid_by_player"][player] = amount
    
    cost = auction_state["participant_costs"][player]
    profit = amount - cost
    
    auction_state["cumulative_profit"][player] = \
        auction_state["cumulative_profit"].get(player, 0) + profit
        
    log_bid(player, amount) 

# ===============================
# DUMMY LOGIC
# ===============================

def process_dummies():

    if not auction_state["active"]:
        return

    now = time.time()

    process_price_chaser(now)
    process_step_dropper(now)
    process_noisy_undercutter(now)

def process_price_chaser(now):

    dummy = "Sarah"

    if now - auction_state["last_actions"][dummy] < random.randint(6, 9):
        return

    auction_state["last_actions"][dummy] = now

    cost = auction_state["participant_costs"][dummy]

    current = auction_state["lowest_bid"] or START_PRICE
    distance = current - cost

    if distance > 50000:
        drop = random.randint(3000, 4500)
    elif distance > 20000:
        drop = random.randint(550, 2200)
    else:
        drop = random.randint(20, 110)

    remaining = AUCTION_DURATION - (time.time() - auction_state["start_time"])

    if remaining < 20:
        drop = int(drop * 1.5)

    bid = current - drop

    if bid >= cost:
        register_bid(dummy, bid)

def process_step_dropper(now):

    dummy = "Noah"

    if now - auction_state["last_actions"][dummy] < random.randint(10, 16):
        return

    auction_state["last_actions"][dummy] = now

    cost = auction_state["participant_costs"][dummy]

    current = auction_state["lowest_bid"] or START_PRICE

    if auction_state["lowest_bid"] is None:
        bid = START_PRICE - random.randint(15000, 30000)
    else:
        distance = current - cost

        if distance > 40000:
            drop = random.randint(5000, 7000)
        elif distance > 15000:
            drop = random.randint(2000, 5400)
        else:
            drop = random.randint(50, 300)

        bid = current - drop

    if bid >= cost:
        register_bid(dummy, bid)

def process_noisy_undercutter(now):

    dummy = "Jenny"

    if now - auction_state["last_actions"][dummy] < random.randint(5, 12):
        return

    auction_state["last_actions"][dummy] = now

    cost = auction_state["participant_costs"][dummy]

    current = auction_state["lowest_bid"] or START_PRICE
    distance = current - cost

    r = random.random()

    if distance > 40000:
        if r < 0.3:
            drop = random.randint(3800, 11000)
        elif r < 0.7:
            drop = random.randint(1000, 4000)
        else:
            drop = random.randint(200, 800)
    else:
        if r < 0.5:
            drop = random.randint(100, 800)
        else:
            drop = random.randint(10, 100)

    bid = current - drop

    if bid >= cost:
        register_bid(dummy, bid)

# ===============================
# RESULTS
# ===============================

def calculate_results():
    print("CALCULATE RESULTS RUNNING")

    try:
        if auction_state["lowest_bidder"] is None:
            return

        winner = auction_state["lowest_bidder"]
        winning_bid = auction_state["lowest_bid"]

        with open(ROUND_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")

            for p in ALL_PLAYERS:
                real_name = auction_state.get("usernames", {}).get(p, p)
                cost = auction_state["participant_costs"][p]

                if p in HUMAN_PLAYERS:
                    round_index = auction_state["round"] - 1
                    matchup = auction_state.get("round_matchups")

                    if matchup:
                        pair = matchup[round_index]
                        if p == "Player A":
                            strategy = strategies[pair[0]]["title"]
                        else:
                            strategy = strategies[pair[1]]["title"]
                    else:
                        strategy = ""
                else:
                    strategy = ""

                if p == winner:
                    profit = winning_bid - cost
                    bonus = round(profit * random.uniform(0.01, 0.02), 2)

                    auction_state["profits"][p] = profit
                    auction_state["bonuses"][p] = bonus

                    auction_state["total_profits"][p] = auction_state["total_profits"].get(p, 0) + profit
                    auction_state["total_bonuses"][p] = auction_state["total_bonuses"].get(p, 0) + bonus

                    total_profit = auction_state["total_profits"][p]

                    writer.writerow([
                        auction_state["round"],
                        real_name,
                        auction_state.get("genders", {}).get(p, ""),
                        True,
                        strategy,
                        cost,
                        profit,
                        bonus,
                        winning_bid,
                        total_profit
                    ])

                else:
                    auction_state["profits"][p] = 0
                    auction_state["bonuses"][p] = 0

                    total_profit = auction_state["total_profits"].get(p, 0)

                    writer.writerow([
                        auction_state["round"],
                        real_name,
                        auction_state.get("genders", {}).get(p, ""),
                        False,
                        strategy,
                        cost,
                        0,
                        0,
                        "",
                        total_profit
                    ])

            f.flush()
            os.fsync(f.fileno())

        update_csv_with_results(winner)

    except Exception as e:
        print("ERROR:", e)

def update_csv_with_results(winner):

    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)

    header = rows[0]
    data = rows[1:]

    current_round = auction_state["round"]

    # Leader bestimmen
    leader = ""
    if auction_state["total_profits"]:
        leader = max(
            auction_state["total_profits"],
            key=auction_state["total_profits"].get
        )

    winner_name = auction_state.get("usernames", {}).get(winner, winner)
    leader_name = auction_state.get("usernames", {}).get(leader, leader)

    for row in data:
        try:
            row_round = int(row[1])
            player = row[2]

            if row_round == current_round:
                if player == winner_name:
                    row[8] = winner_name

                row[9] = leader_name

        except:
            pass

    with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(header)
        writer.writerows(data)  
# ===============================
# DEBUG
# ===============================

@app.route("/debug")
def debug():
    return {
        "active_players": active_players,
        "session": session.get("player")
    }
    
@app.route("/reset_players", methods=["POST"])
def reset_players():
    with player_lock:
        active_players.clear()
    return jsonify({"status": "reset", "active_players": active_players})

@app.route("/goodbye")
def goodbye():
    return render_template("goodbye.html")
# ===============================
# RUN
# ===============================

if __name__ == "__main__":

    initialize_logging()

    app.run(debug=True, use_reloader=False)