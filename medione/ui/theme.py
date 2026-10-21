"""Stylesheet on top of the Streamlit theme in .streamlit/config.toml (clinical teal + white)."""
import streamlit as st

CSS = """
<style>
:root { --tm-teal:#0F766E; --tm-teal-2:#14B8A6; --tm-mint:#E6F4F1; --tm-ink:#0F2A33; --tm-muted:#5B7480;
        --tm-line:#D3E4E2; --tm-card:#FFFFFF; --tm-red:#B91C1C; --tm-amber:#B45309; --tm-blue:#0E7490; }
.block-container { padding-top: 1.3rem; padding-bottom: 180px; max-width: 1240px; }  /* room for the Medi toy */
h1, h2, h3, h4 { color: var(--tm-ink); letter-spacing: -0.01em; }

/* Bordered containers become soft white cards */
[data-testid="stVerticalBlockBorderWrapper"] { background: var(--tm-card); border-radius: 14px !important; }
[data-testid="stVerticalBlockBorderWrapper"] { box-shadow: 0 1px 2px rgba(15,42,51,.04), 0 6px 18px rgba(15,42,51,.05); }
[data-testid="stExpander"] details { background: var(--tm-card); border-radius: 12px; }

/* Brand */
.tm-brand { display:flex; align-items:center; gap:.6rem; font-weight:800; font-size:1.18rem; color:var(--tm-ink); }
.tm-brand .dot { width:34px; height:34px; border-radius:10px; background:linear-gradient(135deg,#14B8A6,#0E7490);
  display:inline-flex; align-items:center; justify-content:center; color:#fff; font-size:1.05rem; box-shadow:0 4px 10px rgba(15,118,110,.35); }
[data-testid="stSidebar"] .tm-brand { color:#fff; }
.tm-tagline { color:#9CC9C3; font-size:.78rem; margin:-.2rem 0 .6rem 2.6rem; }

/* Sidebar navigation */
.tm-nav-group { color:#7FB7B0; font-size:.7rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase;
  margin:.9rem 0 .55rem .35rem; }
[class*="st-key-nav_"] button { justify-content:flex-start !important; padding:.38rem .7rem !important; min-height:2.2rem;
  border-radius:10px !important; border:none !important; }
[class*="st-key-nav_"] button > div { justify-content:flex-start !important; }
[class*="st-key-nav_"] button[kind="tertiary"]:hover { background: rgba(255,255,255,.08) !important; }
[class*="st-key-nav_"] button[kind="primary"] { background: rgba(45,212,191,.16) !important; color:#fff !important;
  box-shadow: inset 3px 0 0 #2DD4BF; }
[data-testid="stSidebar"] [data-testid="stElementContainer"] { margin-bottom:-.45rem; }
.st-key-nav_signout button { border:1px solid #1E5E5C !important; }

/* Page header */
.tm-page { display:flex; align-items:center; gap:.85rem; margin:.2rem 0 1rem; }
.tm-page .ic { width:46px; height:46px; border-radius:14px; background:var(--tm-mint); color:var(--tm-teal);
  display:flex; align-items:center; justify-content:center; flex:none; }
.tm-page h2 { margin:0; padding:0; font-size:1.6rem; font-weight:800; }
.tm-page .sub { color:var(--tm-muted); font-size:.92rem; margin-top:.1rem; }
.tm-sub { color:var(--tm-muted); font-size:.92rem; margin-top:-.4rem; }

/* Dashboard hero */
.tm-hero { background: linear-gradient(120deg,#0F766E 0%,#0E7490 60%,#155E75 100%); color:#fff; border-radius:18px;
  padding:1.3rem 1.5rem; display:flex; justify-content:space-between; gap:1.2rem; flex-wrap:wrap;
  box-shadow:0 10px 28px rgba(14,116,144,.25); position:relative; overflow:hidden; }
.tm-hero:after { content:""; position:absolute; right:-60px; top:-60px; width:220px; height:220px; border-radius:50%;
  background: rgba(255,255,255,.07); }
.tm-hero h1 { color:#fff; font-size:1.65rem; margin:0; padding:0; font-weight:800; }
.tm-hero .date { color:#BFEDE6; font-size:.9rem; }
.tm-hero .who { margin-top:.35rem; color:#E0F7F3; font-size:.95rem; }
.tm-hero .facts { display:flex; gap:.5rem; flex-wrap:wrap; align-items:flex-start; z-index:1; max-width:560px; }
.tm-chip { background: rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.22); border-radius:12px; padding:.45rem .7rem;
  font-size:.82rem; color:#fff; }
.tm-chip b { display:block; font-size:.68rem; letter-spacing:.06em; text-transform:uppercase; color:#BFEDE6; font-weight:700; }
.tm-chip.alert { background: rgba(254,226,226,.95); color:#7F1D1D; border-color:#FCA5A5; }
.tm-chip.alert b { color:#B91C1C; }

/* Stat tiles */
.tm-tile { background:#fff; border:1px solid var(--tm-line); border-radius:16px; padding:1rem 1.1rem; height:100%;
  box-shadow: 0 1px 2px rgba(15,42,51,.04), 0 6px 18px rgba(15,42,51,.05); display:flex; gap:.85rem; align-items:flex-start; }
.tm-tile .ic { width:42px; height:42px; border-radius:12px; display:flex; align-items:center; justify-content:center; flex:none; }
.tm-tile .lbl { color:var(--tm-muted); font-size:.8rem; font-weight:600; }
.tm-tile .val { font-size:1.75rem; font-weight:800; color:var(--tm-ink); line-height:1.15; }
.tm-tile .hint { color:var(--tm-muted); font-size:.78rem; }
.ic-teal { background:#E6F4F1; color:#0F766E; } .ic-blue { background:#E0F2FE; color:#0369A1; }
.ic-amber { background:#FEF3C7; color:#B45309; } .ic-red { background:#FEE2E2; color:#B91C1C; }
.ic-violet { background:#EDE9FE; color:#6D28D9; } .ic-gray { background:#F1F5F9; color:#475569; }

/* Section titles inside cards */
.tm-sec { display:flex; align-items:center; gap:.5rem; font-weight:700; font-size:1.02rem; color:var(--tm-ink); margin-bottom:.35rem; }
.tm-sec .count { background:var(--tm-mint); color:var(--tm-teal); border-radius:999px; font-size:.72rem; padding:.05rem .5rem; }

/* Appointment date block */
.tm-appt { display:flex; gap:.85rem; align-items:center; }
.tm-date { width:58px; flex:none; text-align:center; border-radius:12px; overflow:hidden; border:1px solid var(--tm-line); background:#fff; }
.tm-date .m { background:var(--tm-teal); color:#fff; font-size:.68rem; font-weight:700; letter-spacing:.08em; padding:.15rem 0; }
.tm-date .d { font-size:1.35rem; font-weight:800; color:var(--tm-ink); padding:.1rem 0 0; line-height:1.2; }
.tm-date .w { font-size:.66rem; color:var(--tm-muted); padding-bottom:.2rem; }

/* Badges & rows */
.tm-badge { display:inline-block; padding:.1rem .55rem; border-radius:999px; font-size:.72rem; font-weight:700;
  border:1px solid transparent; white-space:nowrap; vertical-align:middle; }
.tm-gray { background:#F1F5F9; color:#334155; border-color:#E2E8F0; }
.tm-blue { background:#E0F2FE; color:#0369A1; border-color:#BAE6FD; }
.tm-teal { background:#E6F4F1; color:#0F766E; border-color:#B7E1DA; }
.tm-green { background:#F0FDF4; color:#15803D; border-color:#BBF7D0; }
.tm-orange, .tm-amber { background:#FFF7ED; color:#B45309; border-color:#FED7AA; }
.tm-red { background:#FEF2F2; color:#B91C1C; border-color:#FECACA; }
.tm-row-title { font-weight:700; color:var(--tm-ink); }
.tm-row-meta { color:var(--tm-muted); font-size:.85rem; }
.tm-todo { display:flex; gap:.6rem; align-items:flex-start; }
.tm-todo .dot { width:10px; height:10px; border-radius:50%; margin-top:.4rem; flex:none; }
.dot-amber { background:#F59E0B; } .dot-red { background:#DC2626; } .dot-blue { background:#0EA5E9; } .dot-gray { background:#94A3B8; }
.tm-year { font-weight:800; color:var(--tm-teal); font-size:.85rem; letter-spacing:.08em; margin:1rem 0 .3rem; }
.tm-kv { display:grid; grid-template-columns: minmax(120px, 210px) 1fr; gap:.4rem .9rem; font-size:.94rem; }
.tm-kv dt { color:var(--tm-muted); } .tm-kv dd { margin:0; color:var(--tm-ink); white-space:pre-wrap; }
.tm-nr { color:#94A3B8; font-style:italic; }
.tm-ai { border-left:3px solid #7C3AED; background:#F5F3FF; padding:.6rem .8rem; border-radius:8px; }
.tm-ai-label { color:#6D28D9; font-weight:700; font-size:.78rem; letter-spacing:.03em; }
.tm-callout { border-radius:12px; padding:.75rem 1rem; font-size:.9rem; }
.tm-callout.red { background:#FEF2F2; border:1px solid #FECACA; color:#7F1D1D; }
.tm-callout.teal { background:#E6F4F1; border:1px solid #B7E1DA; color:#134E4A; }

/* Emergency card */
.tm-ecard { max-width:560px; border-radius:18px; overflow:hidden; border:2px solid #DC2626; background:#fff;
  box-shadow:0 10px 26px rgba(185,28,28,.12); }
.tm-ecard .top { background:#DC2626; color:#fff; padding:.7rem 1rem; font-weight:800; letter-spacing:.04em; display:flex; justify-content:space-between; }
.tm-ecard .body { padding:1rem 1.1rem; display:grid; grid-template-columns: 1fr 1fr; gap:.7rem 1rem; }
.tm-ecard .k { font-size:.7rem; color:#7F1D1D; font-weight:700; letter-spacing:.06em; text-transform:uppercase; }
.tm-ecard .v { font-size:.98rem; color:#0F2A33; font-weight:600; }
.tm-ecard .full { grid-column: 1 / -1; }
.tm-ecard .bg { font-size:2rem; font-weight:800; color:#B91C1C; }

/* ── Medi, the floating helper toy ─────────────────────────────── */
.st-key-tm_bot, .st-key-tm_bot_open { position:fixed !important; right:22px; bottom:16px; z-index:999990;
  width:112px !important; height:150px; }
.st-key-tm_bot > div, .st-key-tm_bot_open > div { position:static; }
.tm-toy { position:absolute; left:0; right:0; bottom:0; display:flex; flex-direction:column; align-items:center;
  pointer-events:none; }
.tm-bot { animation: tm-float 3.2s ease-in-out infinite; filter: drop-shadow(0 8px 14px rgba(14,116,144,.35)); }
.tm-bot .tm-eyes { transform-origin: 60px 47px; animation: tm-blink 4.5s infinite; }
.tm-bot .tm-arm { transform-origin: 99px 98px; animation: tm-wave 2.4s ease-in-out infinite; }
.tm-bot .tm-ant { animation: tm-glow 1.6s ease-in-out infinite; }
.tm-bot .tm-shadow { animation: tm-shadow 3.2s ease-in-out infinite; transform-origin: 60px 124px; }
.tm-bubble { background:#fff; color:#0F766E; font-weight:800; font-size:.78rem; padding:.35rem .6rem; border-radius:12px;
  border:2px solid #14B8A6; white-space:nowrap; margin-bottom:2px; position:relative; box-shadow:0 6px 16px rgba(15,42,51,.15);
  animation: tm-pop 3.2s ease-in-out infinite; }
.tm-bubble:after { content:""; position:absolute; bottom:-7px; left:50%; margin-left:-6px; border:6px solid transparent;
  border-top-color:#14B8A6; border-bottom:0; }
.st-key-tm_bot_open .tm-bubble { visibility:hidden; }
.st-key-tm_bot_open .tm-bot { animation-duration: 1.6s; }
.st-key-tm_bot [data-testid="stElementContainer"]:has(.stButton),
.st-key-tm_bot_open [data-testid="stElementContainer"]:has(.stButton) { position:absolute !important; inset:0; z-index:2; }
.st-key-tm_bot_toggle button { width:100% !important; height:150px !important; background:transparent !important;
  border:none !important; color:transparent !important; box-shadow:none !important; cursor:pointer; border-radius:24px !important; }
.st-key-tm_bot_toggle button:focus-visible { outline:3px solid #2DD4BF !important; }
.st-key-tm_bot_toggle button p { font-size:1px; }
.st-key-tm_bot:hover .tm-bot { transform: scale(1.06); animation-play-state: paused; }
@keyframes tm-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-9px); } }
@keyframes tm-shadow { 0%,100% { transform: scaleX(1); opacity:.15; } 50% { transform: scaleX(.75); opacity:.08; } }
@keyframes tm-blink { 0%,90%,100% { transform: scaleY(1); } 94% { transform: scaleY(.1); } }
@keyframes tm-wave { 0%,100% { transform: rotate(0deg); } 25% { transform: rotate(-28deg); } 50% { transform: rotate(6deg); }
  75% { transform: rotate(-20deg); } }
@keyframes tm-glow { 0%,100% { fill:#F59E0B; } 50% { fill:#FDE68A; } }
@keyframes tm-pop { 0%,70%,100% { transform: scale(1); } 80% { transform: scale(1.08); } 90% { transform: scale(.97); } }
@media (prefers-reduced-motion: reduce) { .tm-bot, .tm-bot *, .tm-bubble { animation: none !important; } }

/* chat panel */
.st-key-tm_bot_panel { position:fixed !important; right:22px; bottom:172px; z-index:999991; width:390px !important;
  max-height: calc(100vh - 200px); overflow-y:auto; overflow-x:hidden; background:#fff; border:1px solid var(--tm-line);
  border-radius:20px; box-shadow:0 20px 50px rgba(15,42,51,.25); padding:0 .9rem .6rem; gap:.35rem;
  animation: tm-panel .22s ease-out; }
@keyframes tm-panel { from { opacity:0; transform: translateY(12px) scale(.98); } to { opacity:1; transform:none; } }
.tm-bot-head { margin:0 -.9rem; padding:.85rem 1rem; background:linear-gradient(120deg,#0F766E,#0E7490); color:#fff;
  display:flex; gap:.6rem; align-items:center; border-radius:20px 20px 0 0; }
.tm-bot-head .av { width:36px; height:36px; border-radius:50%; background:rgba(255,255,255,.18); display:flex;
  align-items:center; justify-content:center; font-size:1.2rem; }
.tm-bot-head b { display:block; font-size:1rem; } .tm-bot-head span { font-size:.76rem; color:#BFEDE6; }
.st-key-tm_bot_close { position:absolute !important; top:12px; right:12px; width:auto !important; z-index:3; }
.st-key-tm_bot_close button { background:rgba(255,255,255,.16) !important; color:#fff !important; border:none !important;
  min-height:2rem; padding:0 .6rem !important; }
.st-key-tm_bot_panel [class*="st-key-bot_sug_"] { display:inline-block; width:auto !important; margin-right:.3rem; }
.st-key-tm_bot_panel [class*="st-key-bot_sug_"] button { border-radius:999px !important; font-size:.8rem; min-height:1.9rem;
  padding:.1rem .7rem !important; background:#E6F4F1 !important; color:#0F766E !important; border:1px solid #B7E1DA !important; }
.st-key-tm_bot_panel [class*="st-key-bot_rec_"] button { justify-content:flex-start !important; font-size:.83rem;
  min-height:2rem; text-align:left; }
.st-key-tm_bot_panel [data-testid="stChatMessage"] { padding:.5rem .4rem; }
.st-key-tm_bot_panel [data-testid="InputInstructions"] { display:none; }
@media (max-width: 640px) {
  .st-key-tm_bot, .st-key-tm_bot_open { right:8px; bottom:8px; transform: scale(.8); transform-origin: bottom right; }
  .st-key-tm_bot_panel { right:8px; left:8px; width:auto !important; bottom:140px; max-height: calc(100vh - 170px); }
}

.st-key-mobile_nav { display:none; }
@media (max-width: 640px) {
  .tm-kv { grid-template-columns: 1fr; } .tm-kv dt { margin-top:.4rem; }
  .st-key-mobile_nav { display:block; }
  .block-container { padding-top: 3.2rem; }
  .tm-hero h1 { font-size:1.3rem; }
  .tm-ecard .body { grid-template-columns: 1fr; }
}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
