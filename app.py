import os, ast, operator
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Load env vars from .env if present
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///calc.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Calculation(db.Model):
    __tablename__ = "calculations"
    id = db.Column(db.Integer, primary_key=True)
    expression = db.Column(db.String(255), nullable=False)
    result = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def as_dict(self):
        return {
            "id": self.id,
            "expression": self.expression,
            "result": self.result,
            "created_at": self.created_at.isoformat(),
        }

# --- Safe arithmetic evaluator using AST ---
_ops = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_unary_ops = {ast.UAdd: operator.pos, ast.USub: operator.neg}

def _eval_node(node):
    if isinstance(node, ast.BinOp) and type(node.op) in _ops:
        return _ops[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _unary_ops:
        return _unary_ops[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if hasattr(ast, "Num") and isinstance(node, ast.Num):  # Py <3.8
        return node.n
    raise ValueError("Unsupported or unsafe expression")

def safe_eval(expr: str):
    expr = expr.strip()
    if len(expr) > 100:
        raise ValueError("Expression too long")
    tree = ast.parse(expr, mode="eval")
    return _eval_node(tree.body)

@app.before_request
def ensure_tables():
    db.create_all()

@app.get("/")
def home():
    return render_template("index.html")

@app.post("/calculate")
def calculate():
    expression = request.form.get("expression", "").strip()
    if not expression:
        flash("Enter an expression.")
        return redirect(url_for("home"))
    try:
        result = safe_eval(expression)
        calc = Calculation(expression=expression, result=str(result))
        db.session.add(calc)
        db.session.commit()
        return redirect(url_for("history"))
    except Exception as e:
        flash(f"Error: {e}")
        return redirect(url_for("home"))

@app.get("/history")
def history():
    rows = Calculation.query.order_by(Calculation.id.desc()).limit(50).all()
    return render_template("history.html", rows=rows)

@app.get("/api/calc")
def api_calc():
    expression = request.args.get("expr", "").strip()
    if not expression:
        return jsonify({"error": "expr query param required"}), 400
    try:
        result = safe_eval(expression)
        calc = Calculation(expression=expression, result=str(result))
        db.session.add(calc)
        db.session.commit()
        return jsonify(calc.as_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
