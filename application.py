import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Obtain information from the database
    rows = db.execute("SELECT * FROM stocks WHERE user_id=:user_id ORDER BY symbol", user_id=session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=session["user_id"])[0]['cash']

    # For Portfilio
    total = cash
    stocks = []
    for index, row in enumerate(rows):
        stock_info = lookup(row['symbol'])

        # making a list of tuple of all the stocks that the user owns
        stocks.append(list((stock_info['symbol'], stock_info['name'], row['amount'], stock_info['price'], round(stock_info['price'] * row['amount'], 2))))
        total += stocks[index][4]

    return render_template("index.html", stocks=stocks, cash=round(cash, 2), total=round(total, 2))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # Retrieve necessary data for transaction
        amount = int(request.form.get("shares"))
        symbol = lookup(request.form.get("symbol"))['symbol']

        if not request.form.get("symbol"):
            return apology("missing symbol", 400)
        elif not request.form.get("shares"):
            return apology("missing shares", 400)
        elif not lookup(symbol):
            return apology("invalid symbol", 400)
        price = lookup(symbol)['price']
        cash = db.execute("SELECT cash FROM users WHERE id=:user", user = session["user_id"])[0]['cash']
        remain_cash = cash - (price * float(amount))
        if remain_cash < 0:
            return apology("can't afford", 400)

        # Check how many shares user owns
        no_of_shares = db.execute("SELECT amount FROM stocks WHERE user_id = :user AND symbol = :symbol",
                          user=session["user_id"], symbol=symbol)

        # Insert new row into the stock table
        if not no_of_shares:
            db.execute("INSERT INTO stocks(user_id, symbol, amount) VALUES (:user, :symbol, :amount)",
                user=session["user_id"], symbol=symbol, amount=amount)

        # update row into the stock table
        else:
            amount += no_of_shares[0]['amount']

            db.execute("UPDATE stocks SET amount = :amount WHERE user_id = :user AND symbol = :symbol",
                user=session["user_id"], symbol=symbol, amount=amount)

        # update user's cash
        db.execute("UPDATE users SET cash = :cash WHERE id = :user",
                          cash=remain_cash, user=session["user_id"])

        # Update history table
        db.execute("INSERT INTO transactions(user_id, symbol, amount, price) VALUES (:user, :symbol, :amount, :price)",
                user=session["user_id"], symbol=symbol, amount=amount, price=round(price*float(amount)))

        # Redirect user to index page with a success message
        flash("Bought!")
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute("SELECT * FROM transactions WHERE user_id=:user ORDER BY history DESC", user=session["user_id"])
    transactions = []
    for row in rows:
        stock_info = lookup(row['symbol'])
        transactions.append(list((stock_info['name'], stock_info['symbol'], row['amount'], row['price'], row['history'])))
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        # look up for the symbol in IEX using api
        stock = lookup(request.form.get("symbol"))

        if not request.form.get("symbol"):
            return apology("missing symbol", 400)
        elif not stock:
            return apology("invalid symbol", 400)
        return render_template("quote.html", stock=stock)
    else:
        return render_template("quote.html", stock="")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure both passwords match
        elif request.form.get("password") != request.form.get("c_password"):
            return apology("passwords don't match", 403)

        # Query database for username if it already exists
        elif db.execute("SELECT * FROM users WHERE username = :username",
                         username=request.form.get("username")):
            return apology("username already taken", 403)

        # Insert user and hash of the password into the table
        db.execute("INSERT INTO users(username, hash) VALUES (:username, :hash)",
                    username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
            username=request.form.get("username"))

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

@app.route("/password", methods=["GET", "POST"])
def password():
    """Change Password"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        # Fetching data from form
        old_password = request.form.get("o_password")
        o_pass = check_password_hash(rows[0]["hash"], old_password)

        # if old password don't match
        if not o_pass:
            return apology("must provide a valid old password", 403)
        # Ensure both passwords match
        elif request.form.get("n_password") != request.form.get("c_password"):
            return apology("passwords don't match", 403)

        # Insert user and hash of the password into the table
        db.execute("UPDATE users SET hash=:hash WHERE id=:user",
                    user=session["user_id"], hash=generate_password_hash(request.form.get("n_password")))
        flash("Password Updated!")

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("password.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":

        # Retrieve necessary data for transaction
        amount = int(request.form.get("shares"))
        symbol = request.form.get("symbol")
        price = lookup(symbol)["price"]
        shares = price * float(amount)

        prior_amount = db.execute("SELECT amount FROM stocks WHERE user_id=:user AND symbol=:symbol", user=session["user_id"], symbol=symbol)[0]['amount']
        remain_amount = prior_amount - amount
        # delete if all the stocks are sold out
        if remain_amount == 0:
            db.execute("DELETE FROM stocks WHERE user_id=:user AND symbol=:symbol", user=session["user_id"], symbol=symbol)
        elif remain_amount < 0:
            return apology("too many shares", 400)
        else:
            db.execute("UPDATE stocks SET amount=:amount WHERE user_id=:user AND symbol=:symbol", user=session["user_id"], symbol=symbol, amount=remain_amount)
        cash = db.execute("SELECT cash FROM users WHERE id=:user", user=session["user_id"])[0]['cash']
        remain_cash = cash + shares
        db.execute("UPDATE users SET cash=:remain_cash WHERE id=:user", user=session['user_id'], remain_cash=remain_cash)
        if not request.form.get("symbol"):
            return apology("missing symbol", 400)
        elif not request.form.get("shares"):
            return apology("missing shares", 400)
        # Update history table
        db.execute("INSERT INTO transactions(user_id, symbol, amount, price) VALUES (:user, :symbol, :amount, :price)",
                user=session["user_id"], symbol=symbol, amount=-amount, price=round(price*float(amount)))

        # Redirect user to index page with a success message
        flash("Sold!")
        return redirect("/")
    # if the user load the page via GET method
    else:
        rows = db.execute("SELECT symbol, amount FROM stocks WHERE user_id=:user", user=session["user_id"])
        stocks = {}
        for row in rows:
            stocks[row['symbol']] = row['amount']
        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
