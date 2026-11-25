
from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import get_db_connection, init_db
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "blog_platform_secret_key"

init_db()

CATEGORIES = ["Technology", "Education", "Programming", "Lifestyle", "Other"]


# HOME PAGE + SEARCH
@app.route("/")
def index():
    search = request.args.get("search", "").strip()

    conn = get_db_connection()

    if search:
        posts = conn.execute("""
            SELECT posts.*, users.username,
            (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) AS like_count
            FROM posts
            JOIN users ON posts.user_id = users.id
            WHERE LOWER(posts.title) LIKE LOWER(?)
               OR LOWER(posts.content) LIKE LOWER(?)
            ORDER BY posts.id DESC
        """, (f"%{search}%", f"%{search}%")).fetchall()
    else:
        posts = conn.execute("""
            SELECT posts.*, users.username,
            (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) AS like_count
            FROM posts
            JOIN users ON posts.user_id = users.id
            ORDER BY posts.id DESC
        """).fetchall()

    comments = conn.execute("""
        SELECT comments.*, users.username
        FROM comments
        JOIN users ON comments.user_id = users.id
        ORDER BY comments.id ASC
    """).fetchall()

    liked_posts = []

    if "user_id" in session:
        rows = conn.execute(
            "SELECT post_id FROM likes WHERE user_id = ?",
            (session["user_id"],)
        ).fetchall()
        liked_posts = [row["post_id"] for row in rows]

    conn.close()

    return render_template(
        "index.html",
        posts=posts,
        comments=comments,
        search=search,
        categories=CATEGORIES,
        liked_posts=liked_posts
    )


# REGISTER
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        conn = get_db_connection()

        try:
            conn.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username, email, password)
            )
            conn.commit()
            flash("Registration successful! Please login.")
            return redirect(url_for("login"))
        except Exception:
            flash("Email already registered!")
        finally:
            conn.close()

    return render_template("register.html")


# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))

        flash("Invalid email or password!")

    return render_template("login.html")


# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# CREATE BLOG
@app.route("/create", methods=["POST"])
def create_post():
    if "user_id" not in session:
        return redirect(url_for("login"))

    title = request.form["title"].strip()
    content = request.form["content"].strip()
    category = request.form.get("category", "Other")

    if not title or not content:
        flash("Title and content cannot be empty!")
        return redirect(url_for("index"))

    if category not in CATEGORIES:
        category = "Other"

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO posts (title, content, user_id, category) VALUES (?, ?, ?, ?)",
        (title, content, session["user_id"], category)
    )
    conn.commit()
    conn.close()

    flash("Blog published successfully!")
    return redirect(url_for("index"))


# EDIT BLOG
@app.route("/edit/<int:post_id>", methods=["GET", "POST"])
def edit_post(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    post = conn.execute(
        "SELECT * FROM posts WHERE id = ? AND user_id = ?",
        (post_id, session["user_id"])
    ).fetchone()

    if not post:
        conn.close()
        flash("Blog not found!")
        return redirect(url_for("index"))

    if request.method == "POST":
        title = request.form["title"].strip()
        content = request.form["content"].strip()

        if not title or not content:
            conn.close()
            flash("Title and content cannot be empty!")
            return redirect(url_for("edit_post", post_id=post_id))

        conn.execute(
            "UPDATE posts SET title = ?, content = ? WHERE id = ? AND user_id = ?",
            (title, content, post_id, session["user_id"])
        )
        conn.commit()
        conn.close()

        flash("Blog updated successfully!")
        return redirect(url_for("index"))

    conn.close()
    return render_template("edit.html", post=post)


# DELETE BLOG
@app.route("/delete/<int:post_id>", methods=["POST", "GET"])
def delete_post(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    conn.execute("""
        DELETE FROM comments WHERE post_id = ?
        AND EXISTS (
            SELECT 1 FROM posts WHERE posts.id = ?
            AND posts.user_id = ?
        )
    """, (post_id, post_id, session["user_id"]))

    conn.execute("""
        DELETE FROM likes WHERE post_id = ?
        AND EXISTS (
            SELECT 1 FROM posts WHERE posts.id = ?
            AND posts.user_id = ?
        )
    """, (post_id, post_id, session["user_id"]))

    result = conn.execute(
        "DELETE FROM posts WHERE id = ? AND user_id = ?",
        (post_id, session["user_id"])
    )

    conn.commit()
    conn.close()

    flash("Blog deleted successfully!" if result.rowcount else "Blog not found!")
    return redirect(url_for("index"))


# ADD COMMENT
@app.route("/comment/<int:post_id>", methods=["POST"])
def add_comment(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    content = request.form["content"].strip()
    conn = get_db_connection()

    post = conn.execute(
        "SELECT id FROM posts WHERE id = ?", (post_id,)
    ).fetchone()

    if post and content:
        conn.execute(
            "INSERT INTO comments (content, post_id, user_id) VALUES (?, ?, ?)",
            (content, post_id, session["user_id"])
        )
        conn.commit()
        flash("Comment added successfully!")
    else:
        flash("Comment or blog post is invalid!")

    conn.close()
    return redirect(url_for("blog_details", post_id=post_id))


# DELETE COMMENT
@app.route("/delete_comment/<int:comment_id>", methods=["POST"])
def delete_comment(comment_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    comment = conn.execute(
        "SELECT post_id FROM comments WHERE id = ? AND user_id = ?",
        (comment_id, session["user_id"])
    ).fetchone()

    if comment:
        post_id = comment["post_id"]
        conn.execute(
            "DELETE FROM comments WHERE id = ? AND user_id = ?",
            (comment_id, session["user_id"])
        )
        conn.commit()
        flash("Comment deleted successfully!")
    else:
        post_id = None
        flash("Comment not found!")

    conn.close()

    if post_id:
        return redirect(url_for("blog_details", post_id=post_id))
    return redirect(url_for("index"))


# LIKE / UNLIKE
@app.route("/like/<int:post_id>", methods=["POST"])
def toggle_like(post_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    post = conn.execute(
        "SELECT id FROM posts WHERE id = ?", (post_id,)
    ).fetchone()

    if not post:
        conn.close()
        flash("Blog post not found!")
        return redirect(url_for("index"))

    existing = conn.execute(
        "SELECT id FROM likes WHERE post_id = ? AND user_id = ?",
        (post_id, session["user_id"])
    ).fetchone()

    if existing:
        conn.execute(
            "DELETE FROM likes WHERE post_id = ? AND user_id = ?",
            (post_id, session["user_id"])
        )
        flash("Like removed!")
    else:
        conn.execute(
            "INSERT INTO likes (post_id, user_id) VALUES (?, ?)",
            (post_id, session["user_id"])
        )
        flash("You liked this blog!")

    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("index"))


# PROFILE
@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    user = conn.execute(
        "SELECT id, username, email FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    if not user:
        conn.close()
        session.clear()
        return redirect(url_for("login"))

    posts = conn.execute(
        "SELECT * FROM posts WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()

    conn.close()
    return render_template("profile.html", user=user, posts=posts)


# BLOG DETAILS
@app.route("/blog/<int:post_id>")
def blog_details(post_id):
    conn = get_db_connection()

    post = conn.execute("""
        SELECT posts.*, users.username,
        (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) AS like_count
        FROM posts
        JOIN users ON posts.user_id = users.id
        WHERE posts.id = ?
    """, (post_id,)).fetchone()

    if not post:
        conn.close()
        flash("Blog post not found!")
        return redirect(url_for("index"))

    comments = conn.execute("""
        SELECT comments.*, users.username
        FROM comments
        JOIN users ON comments.user_id = users.id
        WHERE comments.post_id = ?
        ORDER BY comments.id ASC
    """, (post_id,)).fetchall()

    liked = False

    if "user_id" in session:
        liked = conn.execute(
            "SELECT id FROM likes WHERE post_id = ? AND user_id = ?",
            (post_id, session["user_id"])
        ).fetchone() is not None

    conn.close()

    return render_template(
        "blog_details.html",
        post=post,
        comments=comments,
        liked=liked
    )


if __name__ == "__main__":
    app.run(debug=True)
