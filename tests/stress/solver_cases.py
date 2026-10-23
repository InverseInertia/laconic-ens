"""Solver stress cases: (name, sheet text, header line, check(record) -> (ok, note)). Run with run_solver_stress.py."""
import numpy as np

def vec(rec, i=0):
    return np.asarray(rec["values"][i]["mag"], float).ravel()

def shifts(n):
    return (f"S1 = hstack(identity({n-1}), zeros({n-1}, 1))\n"
            f"S2 = hstack(zeros({n-1}, 1), identity({n-1}))\n")

def rosen(n, method=None, start="-1.2"):
    t = shifts(n) + f"x = {start} * ones({n}, 1)\n"
    t += "a = S1 * x\nb = S2 * x\n"   # unused, makes sure ordinary lines coexist
    t += "!minimize x\n  objective: sum(100 * (S2 * x - (S1 * x) .* (S1 * x)) .* (S2 * x - (S1 * x) .* (S1 * x)) + (1 - S1 * x) .* (1 - S1 * x))\n"
    if method: t += f"  method: {method}\n"
    t += "  maxiter: 20000\n  timeout: 240\n"
    line = t.split("\n").index("!minimize x") + 1
    return t, line, lambda r: (np.allclose(vec(r), 1, atol=1e-3), f"max|x-1| = {np.max(np.abs(vec(r)-1)):.2e}, f = {r['obj']['mag']:.2e}")

def broyden_tri(n, method=None):
    # F_i = (3 - 2 x_i) x_i - x_{i-1} - 2 x_{i+1} + 1 = 0   (More, Garbow, Hillstrom)
    t = (f"L = vstack(zeros(1, {n}), hstack(identity({n-1}), zeros({n-1}, 1)))\n"
         f"U = transpose(L)\nx = -1 * ones({n}, 1)\n"
         f"!root x\n  equation: (3 - 2 * x) .* x - L * x - 2 * U * x + ones({n}, 1) = zeros({n}, 1)\n  timeout: 240\n"
         + (f"  method: {method}\n" if method else ""))
    def check(r):
        x = vec(r); xp = np.r_[0, x[:-1]]; xn = np.r_[x[1:], 0]
        F = (3 - 2*x)*x - xp - 2*xn + 1
        return np.max(abs(F)) < 1e-6, f"max|F| = {np.max(abs(F)):.1e}"
    return t, 4, check

def hs71(method=None):
    t = ("x = [1; 5; 5; 1]\n!minimize x\n"
         "  objective: elem(x,1,1)*elem(x,4,1)*(elem(x,1,1)+elem(x,2,1)+elem(x,3,1)) + elem(x,3,1)\n"
         "  constraint: elem(x,1,1)*elem(x,2,1)*elem(x,3,1)*elem(x,4,1) >= 25\n"
         "  constraint: dot(x, x) = 40\n  bounds x: 1 .. 5\n")
    if method: t += f"  method: {method}\n"
    ref = np.array([1.0, 4.74299963, 3.82114998, 1.37940829])
    return t, 2, lambda r: (np.allclose(vec(r), ref, atol=1e-3) and abs(r["obj"]["mag"]-17.0140173) < 1e-3,
                            f"f = {r['obj']['mag']:.6f} (ref 17.014017), x = {np.round(vec(r),4)}")

CASES = []
def case(name, text, line, check, expect="done"):
    CASES.append(dict(name=name, text=text, line=line, check=check, expect=expect))

# ---- unconstrained, classic
case("Rosenbrock 2D, BFGS from (-1.2, 1)",
     "x = -1.2\ny = 1\n!minimize x, y\n  objective: 100*(y - x^2)^2 + (1 - x)^2\n", 3,
     lambda r: (np.allclose([vec(r,0)[0], vec(r,1)[0]], 1, atol=1e-4), f"x,y = {vec(r,0)[0]:.6f}, {vec(r,1)[0]:.6f}"))
for n in (10, 50):
    case(f"Rosenbrock {n}D vector unknown, BFGS", *rosen(n))
case("Rosenbrock 10D, L-BFGS-B", *rosen(10, "L-BFGS-B"))
case("Rosenbrock 10D, Nelder-Mead", *rosen(10, "Nelder-Mead"))
case("Rosenbrock 10D, Powell", *rosen(10, "Powell"))
case("Rosenbrock 100D, L-BFGS-B", *rosen(100, "L-BFGS-B"))
case("Rosenbrock 20D, TNC", *rosen(20, "TNC"))
case("Rosenbrock 30D, trust-constr", *rosen(30, "trust-constr"))
# 12 separate scalar unknowns in the header (a chain-coupled quadratic)
names = [f"q_{i}" for i in range(1, 13)]
t = "".join(f"{n} = 0\n" for n in names) + "!minimize " + ", ".join(names) + "\n  objective: " + " + ".join(
    [f"({names[0]} - 1)^2"] + [f"({b} - {a} - 1)^2" for a, b in zip(names, names[1:])]) + "\n"
case("12 scalar unknowns (chain), BFGS", t, 13,
     lambda r: (np.allclose([vec(r,i)[0] for i in range(12)], np.arange(1,13), atol=1e-4), f"q = {[round(vec(r,i)[0],4) for i in (0,5,11)]} (want 1, 6, 12)"))
case("Himmelblau (4 minima) from (0,0)",
     "x = 0\ny = 0\n!minimize x, y\n  objective: (x^2 + y - 11)^2 + (x + y^2 - 7)^2\n", 3,
     lambda r: (r["obj"]["mag"] < 1e-8, f"found ({vec(r,0)[0]:.4f}, {vec(r,1)[0]:.4f}), f = {r['obj']['mag']:.1e}"))
case("Rastrigin 5D (multimodal) from 2.3",
     "x = 2.3 * ones(5, 1)\n!minimize x\n  objective: 50 + sum(x .* x - 10 * cos(2 * pi * x))\n", 2,
     lambda r: (r["obj"]["mag"] < 1e-6, f"f = {r['obj']['mag']:.3f} (global min 0), x = {np.round(vec(r),3)}"))

# ---- roots
for n in (10, 100, 300, 1000):
    case(f"Broyden tridiagonal system n={n}, hybr", *broyden_tri(n))
case("Broyden tridiagonal system n=1000, krylov", *broyden_tri(1000, "krylov"))
case("Triple root x^3 = 0 (singular Jacobian)", "x = 1\n!root x\n  equation: x^3 = 0\n", 2,
     lambda r: (abs(vec(r)[0]) < 1e-3, f"x = {vec(r)[0]:.2e}"))
case("Powell badly scaled system",
     "x = 0\ny = 1\n!root x, y\n  equation: 10000 * x * y = 1\n  equation: exp(-x) + exp(-y) = 1.0001\n", 3,
     lambda r: (abs(vec(r,0)[0]-1.098159e-5) < 1e-8, f"x = {vec(r,0)[0]:.6e} (ref 1.098159e-5), y = {vec(r,1)[0]:.4f}"))
case("Unit-heavy 3x3: truss-like with kN, mm, GPa",
     "E = 200'GPa\nA = 500'mm^2\nL0 = 2'm\nP = 30'kN\n"
     "u = 1'mm\nv = 1'mm\nN = 1'kN\n"
     "!root u, v, N\n  equation: N = E * A * (u + v) / L0\n  equation: N = P - 1000'kN / 'm * v\n  equation: u = 2 * v\n", 8,
     lambda r: (True, "u,v,N = " + ", ".join(f"{vec(r,i)[0]:.5g} {r['values'][i]['unit']}" for i in range(3))))
case("CoolProp inside the residual: Tsat(5 bar) by brentq",
     "T = 400'K\n!root T\n  equation: props(\"P\", \"T\", T, \"Q\", 0, \"Water\") = 5'bar\n  bounds: 300'K .. 500'K\n", 2,
     lambda r: (abs(vec(r)[0]-424.98) < 0.05, f"T = {vec(r)[0]:.3f} K (ref ~424.98)"))
case("CoolProp inside the residual: Tsat(5 bar) by hybr",
     "T = 400'K\n!root T\n  equation: props(\"P\", \"T\", T, \"Q\", 0, \"Water\") = 5'bar\n", 2,
     lambda r: (abs(vec(r)[0]-424.98) < 0.05, f"T = {vec(r)[0]:.3f} K"))

# ---- constrained
case("HS71, SLSQP (default with constraints)", *hs71())
case("HS71, trust-constr", *hs71("trust-constr"))
case("HS71 without the equality, COBYLA",
     "x = [1; 5; 5; 1]\n!minimize x\n  objective: elem(x,1,1)*elem(x,4,1)*(elem(x,1,1)+elem(x,2,1)+elem(x,3,1)) + elem(x,3,1)\n"
     "  constraint: elem(x,1,1)*elem(x,2,1)*elem(x,3,1)*elem(x,4,1) >= 25\n  bounds x: 1 .. 5\n  method: COBYLA\n  maxiter: 5000\n", 2,
     lambda r: (r["obj"]["mag"] < 16.5, f"f = {r['obj']['mag']:.4f}"))
n = 40
case(f"{n} vector inequality constraints x_i >= i/10, minimize sum(x.*x)",
     f"k = [{'; '.join(str(i/10) for i in range(1, n+1))}]\nx = 5 * ones({n}, 1)\n!minimize x\n  objective: sum(x .* x)\n  constraint: x >= k\n", 3,
     lambda r: (np.allclose(vec(r), np.arange(1, n+1)/10, atol=1e-5), f"max err {np.max(abs(vec(r)-np.arange(1,n+1)/10)):.1e}"))
case(f"{n} constraints, trust-constr",
     f"k = [{'; '.join(str(i/10) for i in range(1, n+1))}]\nx = 5 * ones({n}, 1)\n!minimize x\n  objective: sum(x .* x)\n  constraint: x >= k\n  method: trust-constr\n", 3,
     lambda r: (np.allclose(vec(r), np.arange(1, n+1)/10, atol=1e-4), f"max err {np.max(abs(vec(r)-np.arange(1,n+1)/10)):.1e}"))
case("Maximize 20 vars: sum(log(x)) on a simplex (eq) + bounds, SLSQP",
     "x = [" + "; ".join(str(0.5 + i*0.1) for i in range(20)) + "]\n!maximize x\n  objective: sum(ln(x))\n  constraint: sum(x) = 20\n  bounds x: 0.01 .. 10\n", 2,
     lambda r: (np.allclose(vec(r), 1, atol=1e-4), f"max|x-1| = {np.max(abs(vec(r)-1)):.1e}, f = {r['obj']['mag']:.2e}"))
case("Beam section in mixed units (mm start, MPa limit, kN load)",
     "M = 120'kN * 'm\nsig_allow = 165'MPa\nb = 100'mm\nh = 300'mm\n"
     "!minimize b, h\n  objective: b * h\n  constraint: M / (b * h^2 / 6) <= sig_allow\n  constraint: h <= 3 * b\n"
     "  bounds b: 50'mm .. 500'mm\n  bounds h: 50'mm .. 1500'mm\n", 5,
     lambda r: (abs(vec(r,1)[0]**3/3/6 - 120e6/165) / (120e6/165) < 1e-3, f"b,h = {vec(r,0)[0]:.2f}, {vec(r,1)[0]:.2f} mm, area {r['obj']['mag']:.1f} {r['obj']['unit']}"))
case("Same beam started in metres (scaling check)",
     "M = 120'kN * 'm\nsig_allow = 165'MPa\nb = 0.1'm\nh = 0.3'm\n"
     "!minimize b, h\n  objective: b * h\n  constraint: M / (b * h^2 / 6) <= sig_allow\n  constraint: h <= 3 * b\n"
     "  bounds b: 0.05'm .. 0.5'm\n  bounds h: 0.05'm .. 1.5'm\n", 5,
     lambda r: (abs((vec(r,1)[0]*1000)**3/3/6 - 120e6/165) / (120e6/165) < 1e-3, f"b,h = {vec(r,0)[0]*1000:.2f}, {vec(r,1)[0]*1000:.2f} mm"))
case("Same beam started in metres, stress constraint in Pa (badly scaled)",
     "M = 120'kN * 'm\nsig_allow = 165'MPa\nb = 0.1'm\nh = 0.3'm\n"
     "!minimize b, h\n  objective: b * h\n  constraint: M / (b * h^2 / 6) -> 'Pa <= sig_allow\n  constraint: h <= 3 * b\n"
     "  bounds b: 0.05'm .. 0.5'm\n  bounds h: 0.05'm .. 1.5'm\n", 5,
     lambda r: (abs((vec(r,1)[0]*1000)**3/3/6 - 120e6/165) / (120e6/165) < 1e-3, f"b,h = {vec(r,0)[0]*1000:.2f}, {vec(r,1)[0]*1000:.2f} mm"))
case("Maximize volume of open box from 1 m^2 sheet (3 vars, eq constraint)",
     "a = 0.5'm\nb = 0.5'm\nc = 0.2'm\n!maximize a, b, c\n  objective: a * b * c\n  constraint: a * b + 2 * c * (a + b) = 1'm^2\n  bounds a: 0.01'm .. 2'm\n  bounds b: 0.01'm .. 2'm\n  bounds c: 0.01'm .. 2'm\n", 4,
     lambda r: (abs(r["obj"]["mag"] - (1/3)**1.5/2) < 1e-5, f"V = {r['obj']['mag']:.6f} (ref {(1/3)**1.5/2:.6f}), a,b,c = {vec(r,0)[0]:.4f},{vec(r,1)[0]:.4f},{vec(r,2)[0]:.4f}"))
case("Discontinuous objective (floor), Nelder-Mead",
     "x = 3.7\n!minimize x\n  objective: floor(x)^2 + (x - 0.5)^2 / 100\n  method: Nelder-Mead\n", 2,
     lambda r: (0 <= vec(r)[0] < 1, f"x = {vec(r)[0]:.4f}"))
case("Discontinuous objective (floor), BFGS default", "x = 3.7\n!minimize x\n  objective: floor(x)^2 + (x - 0.5)^2 / 100\n", 2,
     lambda r: (0 <= vec(r)[0] < 1, f"x = {vec(r)[0]:.4f}"))

# ---- supervision
case("Heavy evaluation with timeout: 3 (must be killed)",
     "x = 1\n!minimize x\n  objective: det(identity(2500)) * x^2\n  method: Nelder-Mead\n  maxiter: 100000\n  timeout: 3\n", 2,
     lambda r: (False, "should not finish"), expect="timeout")
