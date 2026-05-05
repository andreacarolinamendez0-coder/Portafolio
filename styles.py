CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&display=swap');

:root {
    --bg:           #000000;
    --bg-1:         #0a0a0a;
    --bg-2:         #111111;
    --bg-3:         #1a1a1a;
    --border:       rgba(255,255,255,0.08);
    --border-hover: rgba(255,255,255,0.16);
    --text:         #f5f5f7;
    --text-2:       #a1a1a6;
    --text-3:       #6e6e73;
    --accent:       #0071e3;
    --green:        #30d158;
    --red:          #ff453a;
    --yellow:       #ffd60a;
    --glass:        rgba(255,255,255,0.04);
    --glass-border: rgba(255,255,255,0.07);
    --radius:       18px;
    --radius-sm:    12px;
    --radius-xs:    8px;
    --shadow:       0 4px 24px rgba(0,0,0,0.6);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 16px;
    line-height: 1.5;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
}

.container { max-width: 1100px; margin: 0 auto; padding: 40px 24px; }

.header {
    text-align: center;
    padding: 56px 40px 48px;
    margin-bottom: 40px;
    border-bottom: 1px solid var(--border);
}

h1 {
    font-size: clamp(2rem, 5vw, 3.2rem);
    font-weight: 600;
    letter-spacing: -0.03em;
    color: var(--text);
    margin-bottom: 8px;
    line-height: 1.1;
}

h2 {
    font-size: 1.5rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    color: var(--text);
    margin-bottom: 24px;
}

.subtitle {
    color: var(--text-3);
    font-size: 0.9rem;
    font-weight: 400;
}

.card {
    background: var(--glass);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius);
    padding: 24px;
    margin-bottom: 16px;
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    transition: border-color 0.2s ease;
}

.card:hover { border-color: var(--border-hover); }

.card h3 {
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-3);
    margin-bottom: 12px;
}

.grid-2 { display: grid; grid-template-columns: repeat(2,1fr); gap: 12px; margin-bottom: 16px; }
.grid-3 { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-bottom: 16px; }
.grid-4 { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 16px; }

@media (max-width: 768px) {
    .grid-4 { grid-template-columns: repeat(2,1fr); }
    .grid-3 { grid-template-columns: repeat(2,1fr); }
    .grid-2 { grid-template-columns: 1fr; }
}

.metric-value {
    font-size: 2rem;
    font-weight: 600;
    letter-spacing: -0.03em;
    line-height: 1;
    margin-bottom: 4px;
}

.metric-sub { font-size: 0.8rem; color: var(--text-3); font-weight: 400; }

.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 10px 20px;
    border-radius: 980px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    border: none;
    transition: all 0.2s ease;
    text-decoration: none;
    letter-spacing: -0.01em;
    white-space: nowrap;
    font-family: inherit;
}

.btn:hover { opacity: 0.86; transform: scale(0.98); }
.btn:active { transform: scale(0.96); }

.btn-primary {
    background: var(--accent);
    color: #fff;
    width: 100%;
    padding: 14px 20px;
    font-size: 0.95rem;
    border-radius: var(--radius-sm);
}

.btn-secondary {
    background: var(--bg-3);
    color: var(--text);
    border: 1px solid var(--border);
}

.btn-ghost {
    background: transparent;
    color: var(--accent);
    border: 1px solid rgba(0,113,227,0.3);
}

.badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 980px;
    font-size: 0.7rem;
    font-weight: 500;
    letter-spacing: 0.02em;
}

.badge-green  { background: rgba(48,209,88,0.12);  color: var(--green);  border: 1px solid rgba(48,209,88,0.2); }
.badge-yellow { background: rgba(255,214,10,0.12); color: var(--yellow); border: 1px solid rgba(255,214,10,0.2); }
.badge-blue   { background: rgba(0,113,227,0.12);  color: #4da3ff;       border: 1px solid rgba(0,113,227,0.2); }
.badge-red    { background: rgba(255,69,58,0.12);  color: var(--red);    border: 1px solid rgba(255,69,58,0.2); }
.badge-gray   { background: rgba(255,255,255,0.06); color: var(--text-3); border: 1px solid var(--border); }

.section-title {
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-3);
    margin: 36px 0 14px;
    display: flex;
    align-items: center;
    gap: 10px;
}

.section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
}

.positivo { color: var(--green); font-weight: 500; }
.negativo { color: var(--red);   font-weight: 500; }

.form-group { margin-bottom: 20px; }

.form-group label {
    display: block;
    font-size: 0.8rem;
    color: var(--text-3);
    margin-bottom: 8px;
    font-weight: 400;
}

.form-input, .form-select {
    width: 100%;
    padding: 12px 16px;
    background: var(--bg-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font-size: 0.9rem;
    font-family: inherit;
    outline: none;
    transition: border-color 0.2s;
    appearance: none;
    -webkit-appearance: none;
}

.form-input:focus, .form-select:focus {
    border-color: var(--accent);
    background: var(--bg-3);
}

.form-input::placeholder { color: var(--text-3); }

.alert {
    padding: 14px 18px;
    border-radius: var(--radius-sm);
    margin-bottom: 20px;
    font-size: 0.875rem;
    line-height: 1.5;
}

.alert-error   { background: rgba(255,69,58,0.08);  border: 1px solid rgba(255,69,58,0.2);  color: #ff6961; }
.alert-success { background: rgba(48,209,88,0.08);  border: 1px solid rgba(48,209,88,0.2);  color: #34c759; }
.alert-info    { background: rgba(0,113,227,0.08);  border: 1px solid rgba(0,113,227,0.2);  color: #4da3ff; }

.nav {
    display: flex;
    gap: 2px;
    margin-bottom: 32px;
    background: var(--bg-2);
    padding: 4px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    width: fit-content;
}

.nav a {
    padding: 8px 18px;
    border-radius: var(--radius-xs);
    font-size: 0.85rem;
    font-weight: 400;
    color: var(--text-3);
    text-decoration: none;
    transition: all 0.15s ease;
}

.nav a:hover { color: var(--text); background: var(--bg-3); }

.nav a.active {
    background: var(--bg-3);
    color: var(--text);
    font-weight: 500;
    border: 1px solid var(--border);
}

.tabs {
    display: flex;
    gap: 2px;
    margin-bottom: 28px;
    background: var(--bg-2);
    padding: 4px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    width: fit-content;
}

.tab {
    padding: 8px 22px;
    border-radius: var(--radius-xs);
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 400;
    color: var(--text-3);
    border: none;
    background: transparent;
    transition: all 0.15s ease;
    font-family: inherit;
}

.tab:hover { color: var(--text); background: var(--bg-3); }

.tab.active {
    background: var(--bg-3);
    color: var(--text);
    font-weight: 500;
    border: 1px solid var(--border);
}

.tab-content { display: none; }
.tab-content.active { display: block; }

.tabla { width: 100%; border-collapse: collapse; }

.tabla th {
    font-size: 0.7rem;
    font-weight: 500;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-3);
    padding: 10px 16px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}

.tabla td {
    padding: 14px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    font-size: 0.875rem;
    color: var(--text-2);
}

.tabla tr:last-child td { border-bottom: none; }
.tabla tbody tr:hover td { background: rgba(255,255,255,0.02); color: var(--text); }
</style>
"""

CSS_SAFE = CSS
