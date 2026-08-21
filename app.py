from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for
from sqlalchemy import create_engine, text

app = Flask(__name__)
DATABASE_PATH = Path(__file__).parent / ".database" / "oscars_gifts.db"
engine = create_engine(f"sqlite:///{DATABASE_PATH}")


def initialise_database():
    """Create the tables used by Oscar's gift collection app if needed."""
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS gifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gift_name TEXT NOT NULL,
                price REAL NOT NULL CHECK (price >= 0)
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS contributions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gift_id INTEGER NOT NULL,
                contributor_name TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount > 0),
                FOREIGN KEY (gift_id) REFERENCES gifts(id)
            )
        """))


initialise_database()


@app.route("/")
def home():
    with engine.connect() as connection:
        # EFFICIENCY 1 — SQLite aggregate: SUM and GROUP BY calculate every gift's
        # total in one query, avoiding a separate contribution query for each gift.
        gifts = connection.execute(text("""
            SELECT gifts.id, gifts.gift_name, gifts.price,
                   COALESCE(SUM(contributions.amount), 0) AS total_contributed
            FROM gifts LEFT JOIN contributions ON contributions.gift_id = gifts.id
            GROUP BY gifts.id, gifts.gift_name, gifts.price ORDER BY gifts.id DESC
        """)).mappings().all()
    return render_template("index.html", gifts=gifts)


@app.route("/add-gift", methods=["GET", "POST"])
def add_gift():
    if request.method == "POST":
        gift_name = request.form["gift_name"].strip()
        try:
            price = float(request.form["price"])
        except ValueError:
            return render_template("add-gift.html", error="Please enter a valid price."), 400
        if not gift_name:
            return render_template("add-gift.html", error="Please enter a gift name."), 400
        if price < 0:
            return render_template("add-gift.html", error="The price cannot be negative."), 400
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO gifts (gift_name, price) VALUES (:gift_name, :price)"), {"gift_name": gift_name, "price": price})
        return redirect(url_for("home"))
    return render_template("add-gift.html")


@app.route("/gifts/<int:gift_id>/remove", methods=["POST"])
def remove_gift(gift_id):
    get_gift(gift_id)
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM contributions WHERE gift_id = :gift_id"),
            {"gift_id": gift_id},
        )
        connection.execute(
            text("DELETE FROM gifts WHERE id = :gift_id"),
            {"gift_id": gift_id},
        )
    return redirect(url_for("home"))


def get_gift(gift_id):
    with engine.connect() as connection:
        gift = connection.execute(text("SELECT id, gift_name, price FROM gifts WHERE id = :gift_id"), {"gift_id": gift_id}).mappings().first()
    if gift is None:
        abort(404)
    return gift


def get_gift_summary(gift_id, connection):
    """Fetch a gift and its running contribution total in one database query."""
    # EFFICIENCY 2 — SQLite LEFT JOIN + COALESCE: this replaces the previous
    # get_gift() query followed by get_total_contributed() query, reducing the
    # add-contribution page from two database round trips to one.
    summary = connection.execute(text("""
        SELECT gifts.id, gifts.gift_name, gifts.price,
               COALESCE(SUM(contributions.amount), 0) AS total_contributed
        FROM gifts
        LEFT JOIN contributions ON contributions.gift_id = gifts.id
        WHERE gifts.id = :gift_id
        GROUP BY gifts.id, gifts.gift_name, gifts.price
    """), {"gift_id": gift_id}).mappings().first()
    if summary is None:
        abort(404)
    return summary


@app.route("/gifts/<int:gift_id>/contributions")
def contributions(gift_id):
    gift = get_gift(gift_id)
    with engine.connect() as connection:
        contribution_list = connection.execute(text("""
            SELECT id, contributor_name, amount FROM contributions
            WHERE gift_id = :gift_id ORDER BY id DESC
        """), {"gift_id": gift_id}).mappings().all()
    # EFFICIENCY 3 — Python generator expression: sum consumes each amount
    # lazily, so Python does not allocate an extra list of amounts first.
    total = sum(contribution["amount"] for contribution in contribution_list)
    remaining = max(gift["price"] - total, 0)
    return render_template(
        "contributions.html", gift=gift, contributions=contribution_list,
        total=total, remaining=remaining,
    )


@app.route("/gifts/<int:gift_id>/add-contribution", methods=["GET", "POST"])
def add_contribution(gift_id):
    with engine.connect() as connection:
        gift = get_gift_summary(gift_id, connection)
    total = gift["total_contributed"]
    remaining = max(gift["price"] - total, 0)

    if request.method == "GET" and remaining <= 0:
        return redirect(url_for("contributions", gift_id=gift_id))

    if request.method == "POST":
        contributor_name = request.form["contributor_name"].strip()
        try:
            amount = float(request.form["amount"])
        except ValueError:
            return render_template("add-contribution.html", gift=gift, remaining=remaining, error="Please enter a valid amount."), 400
        if not contributor_name:
            return render_template("add-contribution.html", gift=gift, remaining=remaining, error="Please enter the contributor's name."), 400
        if amount <= 0:
            return render_template("add-contribution.html", gift=gift, remaining=remaining, error="The amount must be greater than zero."), 400
        with engine.begin() as connection:
            current_gift = get_gift_summary(gift_id, connection)
            current_remaining = max(current_gift["price"] - current_gift["total_contributed"], 0)
            if current_remaining <= 0:
                return render_template("add-contribution.html", gift=gift, remaining=0, error="This gift has already been fully funded."), 400
            if amount > current_remaining:
                return render_template("add-contribution.html", gift=gift, remaining=current_remaining, error=f"The contribution cannot be more than the ${current_remaining:.2f} still needed."), 400
            connection.execute(text("""
                INSERT INTO contributions (gift_id, contributor_name, amount)
                VALUES (:gift_id, :contributor_name, :amount)
            """), {"gift_id": gift_id, "contributor_name": contributor_name, "amount": amount})
        return redirect(url_for("contributions", gift_id=gift_id))
    return render_template("add-contribution.html", gift=gift, remaining=remaining)


@app.route("/gifts/<int:gift_id>/contributions/<int:contribution_id>/remove", methods=["POST"])
def remove_contribution(gift_id, contribution_id):
    get_gift(gift_id)
    with engine.begin() as connection:
        connection.execute(text("""
            DELETE FROM contributions
            WHERE id = :contribution_id AND gift_id = :gift_id
        """), {"contribution_id": contribution_id, "gift_id": gift_id})
    return redirect(url_for("contributions", gift_id=gift_id))


if __name__ == "__main__":
    app.run(debug=True, reloader_type="stat", port=5000)
