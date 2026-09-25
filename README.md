# the poker project

Live site: https://pokerproject.architgoswami.com

That address is GitHub Pages. Models and the live dealer run in the browser from the same Python rules. A friends table still needs the server in this folder, because Pages cannot keep a shared room open between two people.

Texas hold'em in the browser. One rules engine runs three tables: opponents you tune, a room code for friends, and a live dealer that follows a real deck.

`poker.py` is the original console script. It prints random cards and can deal the same card twice. The room in this folder replaces that with a 52-card deck, betting, and a page at http://127.0.0.1:8765.

## Run it

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m app
```

Open http://127.0.0.1:8765.

Tests:

```powershell
.\.venv\Scripts\python -m pytest
```

Rooms and dealer sessions live in memory. Restarting the server clears every table.

## Features

### Models

Seat up to five bots, with or without yourself. Six seats is the table limit, so a full table is you plus five models.

Each model has a style and three sliders, 0 to 100:

| Style | Looseness | Aggression | Bluff |
| --- | --- | --- | --- |
| Conservative | 18 | 34 | 3 |
| Super casual | 80 | 22 | 8 |
| Balanced | 44 | 60 | 12 |
| Reckless | 90 | 94 | 40 |

Moving a slider away from those numbers marks the player Custom. The label is only a name. The three numbers decide the line.

Before the flop, strength comes from pair rank, suitedness, connectedness, and whether an ace is in the hand. After the flop, it comes from the best five-card hand, with extra credit for a flush draw or an open-ended straight. That score is shifted by looseness, then compared with the price of a call. Aggression changes bet size. Low aggression often min-raises. High aggression bets a larger fraction of the pot, and sometimes shoves.

Leave "I'll play" unchecked and the table deals itself. Hole cards stay face up so you can watch June fold and Marlow call. "Pause the models" stops the auto-deal after the current hand. A friend who joins that table stops the reveal, so a second browser cannot watch their cards.

You are the big blind on the first hand when you sit with bots, so you see them act before you do. Later hands the button moves.

### Friends

Create a table and the page shows a four-letter code. The alphabet skips I, O, 0, and 1. Copy invite builds `/?room=CODE`, which opens the join form with the code filled in.

Someone can sit only while a hand is not in progress, and only if a seat is free. Everyone buys in for the same stack. Hole cards are sent only to their owner until showdown. Folded cards stay down. The host, or any seated human, can deal the next hand.

If it is your turn, Fold, Check, Call, and Raise are the legal buttons. F folds when a bet is facing you. C checks or calls. The raise slider runs from the minimum raise to an all-in.

### Live dealer

This mode records a game that is already happening. It does not shuffle. You name two to six seats, pick which seat gets the advice, and set the stack and blinds. Opening the station posts the blinds and starts a hand. The first hand puts you in the big blind.

Say the action, or type it. Listening uses the browser speech API, which works in Chrome and Edge. Each line is parsed into an event:

- `Alex folds`, `Sam checks`, `I call`, `Alex bets 20`, `Sam raises to 60`, `Alex all in`
- `my cards are ace of spades and ace of hearts`, or two card codes such as `As Kh`
- `Alex has ace of spades and king of hearts`
- `flop ace of spades king of hearts seven of clubs`
- `turn ten of diamonds`, `river two of clubs`
- `new hand`, `undo`, `pot is 150`, `small blind 1`, `big blind 2`

Cards can be words (`ace of spades`) or codes (`As`, `10h`). A new street clears the bets in front of each player and keeps the pot. Saying the same street again corrects the cards and leaves the bets alone.

Advice needs your two cards. It deals the rest of the board about 160 times against the players who have not folded, and compares that win chance with the pot odds. With nothing to call, about 62% or better suggests a bet. Facing a bet, a hand well ahead of the price suggests a raise. A hand that cannot meet the price suggests a fold. Everything else suggests a call.

The rank-and-suit buttons add one card at a time to your hand or the board. Clear and undo are there because speech gets a sentence wrong. Scan a card only after you hold one card up on a plain background. Confirm "my card" or "board" before it counts.

### Shared table rules

Every digital hand uses one deck. One card is burned before each street. Blinds are posted by the small blind and big blind. Heads-up, the button posts the small blind and acts first before the flop. With three or more players, the first action is the seat left of the big blind, and the first action after the flop is the seat left of the button.

A raise is "to" an amount for that street. The minimum raise is the size of the last full raise, starting at the big blind. An all-in for less than that minimum is allowed and does not let players who already acted raise again.

If everyone else folds, the last player takes the pot and cards stay hidden. If more than one player remains and nobody can bet, the board is run out and the hands are shown. Side pots pay the best hand that matched each contribution. An odd chip in a tie goes to the winner closest to the left of the button. A player with no chips sits out the next hand. One player with all the chips ends the game.

## Options

Set these before you open a table:

- Your name, 1 to 18 characters. Names at one table have to be distinct.
- Buy-in. It has to cover the big blind, and it cannot be more than 100,000.
- Small blind and big blind. The big blind has to be larger than the small blind. The big blind cannot be more than 10,000. Defaults are 10 and 20 on a digital table, and 1 and 2 on the live dealer.
- Models: style preset, then looseness, aggression, and bluff.
- "I'll play" on a models table. Off means you watch.
- Live dealer: which seat is you, and a stack that covers the big blind.

At the table you can deal the next hand, pause or resume auto-dealing on a models table, and copy the invite link.

## Tech stack

The server is Python. The page is static HTML, CSS, and JavaScript, with no frontend framework.

| Piece | Role |
| --- | --- |
| FastAPI | HTTP routes for tables, dealer commands, and card scans |
| Uvicorn | Serves the app on `127.0.0.1:8765` |
| `websockets` | Required so Uvicorn can accept the table socket. Without it, the page creates a table and the socket fails |
| Pydantic | Request bodies for creating a table, joining, and dealer commands |
| `python-multipart` | The scan upload |
| Browser `WebSocket` | One connection per seated player or watcher |
| Browser `SpeechRecognition` | Live dealer microphone. Chrome and Edge |
| `getUserMedia` | Live dealer camera |
| Pillow, NumPy, OpenCV | Optional card scan. If they are missing, scan returns an error and voice plus the card buttons still work |
| pytest | Hand ranks, side pots, chip conservation across bot hands, and the speech parser |

Layout:

- `app/engine.py` deals, bets, and ranks hands
- `app/ai.py` turns a style into a legal action
- `app/rooms.py` keeps tables, sockets, and the bot turn loop
- `app/dealer.py` tracks a physical hand and prices yours
- `app/vision.py` reads one card from a still
- `app/main.py` is the HTTP and socket API
- `static/` is the page
- `tests/` covers the engine and the dealer parser

## Challenges

**One action can change the whole street.** Checking the big blind option ends the pre-flop round. A fold can end the hand. An all-in can mean the board should be dealt with no more betting. The engine applies the click, then walks streets until a human or a bot still has a decision. Getting that walk wrong either skips a player or loops.

**Short all-ins.** A player who cannot reach the minimum raise may still move all-in. That extra money raises the amount others must call, and it does not give the original raiser another turn. Tracking this is an `acted` flag that resets only on a full raise.

**Side pots.** Three players putting in 100, 300, and 300 is not one pot of 700. The first 100 from each player is a main pot all three can win. The other 400 is a side pot between the two who covered it. Folded chips stay in the pot and cannot win it. Tests lock a known board so the short stack wins only the main pot.

**Chips have to come back.** Every bet leaves a stack and enters the pot. Showdown and a fold-win put that sum back. A random 20-hand session with three different styles checks that the stacks still add up to the starting total.

**Bots have to stay legal.** The style function can aim at a raise that is below the minimum or above the stack. A second step clamps it to check, call, fold, min-raise, or all-in. The server still catches a bad action and falls back, so a bot cannot freeze the table on its own turn.

**Styles that are actually different.** A single "play well" score makes every seat look the same. Looseness shifts how strong a hand feels, aggression changes the size, and bluff is a separate roll. Conservative and reckless use the same evaluator and still fold and call different hands.

**Who can see which cards.** The socket for each player builds its own snapshot. Your hole cards are included. Theirs are `??` until showdown. A models watch session sets reveal for every connection. The moment a human sits down, reveal turns off. Otherwise the watch tab would be a way to see a friend's hand.

**Bot timing versus a human click.** Bots wait most of a second so the log is readable. The wait happens outside the table lock. After the wait, the server checks that it is still that bot's turn before it clicks. A pause during the pause between hands cancels the next deal.

**Speech is a grammar, not a conversation.** "Raises to 60" and "bets 20" both have to become a stack update. "I call" has to mean the advised seat. "Flop" needs three cards, and a second flop is a correction rather than a new round of betting. Duplicate cards are rejected. Undo restores the last snapshot, including a mistaken new hand. Sentences outside that grammar return "I didn't catch that."

**The camera is the weak sensor.** The scan looks for a four-corner contour with a card-shaped ratio, warps it, and template-matches the corner against drawn ranks and suits. Red pixels choose hearts or diamonds versus spades or clubs. That fails when the card is tilted, glossy, or poorly lit, so a guess under the confidence cutoff is discarded, and a guess above it still waits for you to confirm the slot. The microphone and the buttons do not depend on that match.

**Default browser controls looked wrong on a dark page.** A checkbox in a CSS grid stretches, so the check mark sat far from its label. Range inputs painted a bright blue thumb. Both are drawn explicitly now: a gold ring for the seat picker, and a thin gold track with a small pearl thumb for every slider.
