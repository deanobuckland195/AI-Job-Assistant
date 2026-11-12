"""Shared career workspace theme. Only static CSS; user content uses native widgets."""

DARK_STYLE = """<style>
:root {
 --ai-bg:#070619; --ai-panel:#120e2b; --ai-border:#594078;
 --ai-text:#faf5ff; --ai-muted:#d5bfe7; --ai-accent:#d3a1ff;
}
/* Paint the visible page shell, not just the outer Streamlit root. */
.stApp, [data-testid="stAppViewContainer"] {
 color-scheme:dark; color:var(--ai-text); background:var(--ai-bg)!important;
}
/* Structural layers must expose the canvas; card/widget surfaces stay intact. */
[data-testid="stMain"], [data-testid="stAppScrollToBottomContainer"],
[data-testid="stMainBlockContainer"] {background:transparent!important}
[data-testid="stHeader"] {
 background:linear-gradient(100deg,#070619,#0b0820)!important; border-bottom:1px solid #4f366b;
}
[data-testid="stMainBlockContainer"] {max-width:1580px; padding:4.5rem 2rem 3rem}
[data-testid="stSidebar"] {background:#100d2c!important; border-right:1px solid #302644}
[data-testid="stSidebarContent"], [data-testid="stSidebarHeader"] {background:transparent!important}
.st-key-brand {border-bottom:1px solid #70448b; padding-bottom:1rem; margin-bottom:.5rem}
.st-key-brand h1 {font-size:1.2rem; letter-spacing:-.035em; font-weight:700}
.st-key-brand h1::before {content:""; display:inline-block; width:.65em; height:.65em; margin-right:.55em;
 border-radius:4px; background:linear-gradient(135deg,#9b5cff,#cf3ca6)}
.st-key-brand [data-testid="stCaptionContainer"] {font-size:.68rem; letter-spacing:.12em}
[data-testid="stSidebar"] [role="radiogroup"] {gap:.35rem}
[data-testid="stSidebar"] [role="radiogroup"] > div {width:100%}
[data-testid="stSidebar"] [role="radiogroup"] label {position:relative; display:flex!important;
 flex-direction:row!important; align-items:center; width:100%!important; box-sizing:border-box;
 padding:.55rem .75rem .55rem 2.5rem; min-height:44px; gap:.65rem; border:1px solid transparent; border-radius:12px}
[data-testid="stSidebar"] [role="radiogroup"] label::before {content:"▦"; position:absolute; left:.85rem;
 top:50%; transform:translateY(-50%); line-height:1; font-size:1.25rem; color:#c8a9ff}
[data-testid="stSidebar"] label:has(input[value="1"])::before {content:"⊕"}
[data-testid="stSidebar"] label:has(input[value="2"])::before {content:"◇"}
[data-testid="stSidebar"] label:has(input[value="3"])::before {content:"◈"}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {background:#1b143c}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {border-color:#986ecc;
 border-left:4px solid #b189ff; background:linear-gradient(110deg,#291851,#211540)}
[data-testid="stSidebar"] label:has(input:focus-visible) {outline:3px solid #e4b5ff; outline-offset:3px}
h1,h2,h3,h4,h5 {color:var(--ai-text); letter-spacing:-.035em; overflow-wrap:anywhere}
h2 {font-size:clamp(1.7rem,3vw,2.4rem); font-weight:700}
h3 {font-size:1.3rem; font-weight:650}
[data-testid="stCaptionContainer"] {color:var(--ai-muted); line-height:1.6}
[data-testid="stCaptionContainer"] p {color:inherit}
[data-testid="stWidgetLabel"] {margin-bottom:.5rem}
[data-testid="stWidgetLabel"] p {color:#f0e0fa; font-weight:550}
a {color:#e7bbff}
a:visited {color:#d6bdff}
hr {border-color:#583d70}
.st-key-dashboard_hero {padding:2.2rem 2.4rem; margin-bottom:.8rem;
 border:1px solid #51326e; border-radius:24px;
 background:radial-gradient(ellipse at 0% 0%,#6b2ba522,transparent 65%),
 linear-gradient(115deg,#160d30,#130b21); box-shadow:inset 0 1px 0 #b77aff0a}
.st-key-dashboard_hero h1 {font-size:clamp(1.8rem,3.2vw,2.6rem); line-height:1.2;
 color:var(--ai-text); letter-spacing:-.04em; padding:.2rem 0 .4rem}
.st-key-dashboard_hero [data-testid="stCaptionContainer"] {font-size:1rem; max-width:760px}
.st-key-hero_actions {margin-top:.6rem; max-width:920px}
.st-key-hero_actions [data-testid="stColumn"] {min-width:0}
.st-key-page_intro {padding:0 0 1.3rem; margin-bottom:.3rem}
.st-key-page_intro h1 {font-size:clamp(2rem,3.7vw,3.25rem); line-height:1.15; letter-spacing:-.04em;
 width:fit-content; max-width:100%; background:linear-gradient(100deg,#eadcff,#b49aff 55%,#79baff);
 background-clip:text; -webkit-background-clip:text; color:transparent}
.st-key-page_intro [data-testid="stCaptionContainer"] {font-size:1.05rem; max-width:880px}
[data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {
 border-color:var(--ai-border)!important; border-radius:20px; background:var(--ai-panel)}
[data-testid="stForm"] {padding:1.6rem; background:linear-gradient(120deg,#20182f,#251c3b)}
[data-testid="stExpander"] {border:1px solid #70448b; border-radius:13px; background:#21172f}
[data-testid="stExpander"] summary {color:var(--ai-text); padding:.8rem 1rem}
[data-testid="stExpander"] summary:hover {background:#38244f; border-radius:12px}
[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button {
 min-height:48px; padding:.55rem 1.1rem; border-radius:12px; border:1px solid #965eaf;
 background:#261443; color:var(--ai-text); font-weight:550; transition:background-color .12s ease}
[data-testid="stButton"] button:hover, [data-testid="stFormSubmitButton"] button:hover {
 border-color:#d3a1ff; background:#3d205e; color:#fff}
button[kind^="primary"], [data-testid="stBaseButton-primary"] {
 background:linear-gradient(110deg,#7b2de2,#b52a8d)!important;
 border:1px solid #db94f5!important; color:#fff!important; box-shadow:0 4px 14px #773cf033}
button[kind^="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
 background:linear-gradient(110deg,#6823c3,#982277)!important}
button:disabled {opacity:1!important; background:#352841!important; color:#d4c1e0!important;
 border-color:#8d719e!important; box-shadow:none!important; cursor:not-allowed}
button:focus-visible, input:focus-visible, textarea:focus-visible, summary:focus-visible,
a:focus-visible, [role="tab"]:focus-visible, [role="spinbutton"]:focus-visible {
 outline:3px solid #e4b5ff!important; outline-offset:3px}
/* Both React-Aria and BaseWeb roots: controls remain visible before focus. */
:is([data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"],
 [data-testid="stNumberInputContainer"], [data-testid="stChatInput"],
 [data-testid="stDateInputField"], .stSelectbox [role="group"], .stMultiSelect div[role="group"],
 [data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div) {
 background-color:#2c2440; border:1px solid #a47ab7; border-radius:12px; color:#faf5ff; opacity:1}
:is([data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"],
 [data-testid="stDateInputField"], .stSelectbox [role="group"], .stMultiSelect div[role="group"]) {min-height:54px}
[data-testid="stTextInputRootElement"] input, .stSelectbox input {min-height:50px; font-size:1rem}
:is([data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"],
 [data-testid="stNumberInputContainer"], [data-testid="stChatInput"],
 [data-testid="stDateInputField"], .stSelectbox [role="group"], .stMultiSelect div[role="group"],
 [data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div):hover {border-color:#c69adb}
:is([data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"],
 [data-testid="stNumberInputContainer"], [data-testid="stChatInput"],
 [data-testid="stDateInputField"], .stSelectbox [role="group"], .stMultiSelect div[role="group"],
 [data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div):focus-within {
 border-color:#d3a1ff; box-shadow:0 0 0 2px #d3a1ff4d}
input, textarea {color:#faf5ff; caret-color:#e4b5ff}
[data-testid="stTextInputRootElement"] input, [data-testid="stTextAreaRootElement"] textarea,
[data-testid="stDateInput"] input {background:transparent}
input::placeholder, textarea::placeholder {color:#dbc5e9!important; opacity:1}
:is([data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"],
 [data-testid="stNumberInputContainer"], [data-testid="stDateInputField"],
 .stSelectbox [role="group"], .stMultiSelect div[role="group"],
 [data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div):is(
 :has(input:disabled), :has(textarea:disabled), :has([aria-disabled="true"])),
[role="group"][aria-disabled="true"], [role="group"][data-disabled="true"] {
 background:#2b1938; border-color:#8d719e; box-shadow:none; opacity:1}
input:disabled, textarea:disabled, [role="combobox"]:disabled, [role="combobox"][aria-disabled="true"] {
 color:#d4c1e0!important; -webkit-text-fill-color:#d4c1e0!important; opacity:1; cursor:not-allowed}
input:disabled::placeholder, textarea:disabled::placeholder {color:#cdb5dd!important; opacity:1}
[data-testid="stDateInput"] [role="group"] {background:transparent; border:0}
[data-testid="stDateInput"] [data-placeholder="true"] {color:#dbc5e9}
[data-testid="stDateInput"] [role="spinbutton"][aria-disabled="true"] {color:#d4c1e0; opacity:1}
.stMultiSelect [data-tag] {background:#6a3a84; border:1px solid #a47ab7; color:#faf5ff; opacity:1}
.stMultiSelect [data-tag] span {color:inherit; opacity:1}
.stMultiSelect [data-disabled="true"] [data-tag] {background:#422854; color:#d4c1e0}
[role="listbox"], [data-baseweb="popover"] {background:#302044; color:var(--ai-text);
 border:1px solid #965eaf; border-radius:12px; box-shadow:0 14px 36px #00052a59}
[role="option"] {color:var(--ai-text)}
[role="option"]:hover, [role="option"][data-focused="true"] {background:#503365}
[role="option"][aria-selected="true"] {background:#67418a; color:#fff}
[role="tablist"] {border-bottom:1px solid #70448b; gap:1.2rem}
[role="tab"] {color:var(--ai-muted)}
[role="tab"][aria-selected="true"] {color:#ead0ff}
[data-testid="stMetric"] {min-width:0; min-height:8rem; padding:1.1rem; border:1px solid #493467;
 border-radius:20px; background:linear-gradient(125deg,#151030,#100d28)}
[data-testid="stMetricLabel"] p {color:var(--ai-muted); white-space:normal; line-height:1.5}
[data-testid="stMetricValue"] {font-variant-numeric:tabular-nums; letter-spacing:-.045em; color:var(--ai-text)}
[data-testid="stMetricValue"] > div {font-size:clamp(1.4rem,2.3vw,2rem); white-space:normal; overflow-wrap:anywhere}
.st-key-overview {margin:0 0 .4rem}
.st-key-overview [data-testid="stHorizontalBlock"] {flex-wrap:wrap; gap:1rem}
.st-key-overview [data-testid="stColumn"] {flex:0 0 calc((100% - 2rem) / 3)!important; min-width:0}
.st-key-overview [data-testid="stMetric"] {min-height:8.5rem; padding:1.25rem 1.4rem}
.st-key-overview [data-testid="stMetricLabel"] p {font-size:.8rem; letter-spacing:.07em; text-transform:uppercase}
.st-key-overview [data-testid="stMetricValue"] > div {font-size:2.1rem; font-weight:650}
.st-key-application_listing {padding:1.4rem; background:transparent; border:1px solid #493467; border-radius:22px}
.st-key-application_summary {padding:1.1rem; background:#1c152e; border:1px solid #634283; border-radius:20px}
.st-key-application_summary [data-testid="stMetric"] {min-height:0; padding:.9rem}
[class*="st-key-application_card_"], .st-key-interview_question_card, .st-key-interview_answer_card,
[class*="st-key-saved_milestone_card_"], [class*="st-key-preview_milestone_card_"] {
 padding:1.2rem; background:linear-gradient(145deg,#1b1235,#130f29); border:1px solid #795399; border-radius:20px}
[class*="st-key-saved_milestone_card_"], [class*="st-key-preview_milestone_card_"] {border-top:3px solid #a97dff}
[class*="st-key-saved_milestone_title_"] [data-testid="stText"],
[class*="st-key-preview_milestone_title_"] [data-testid="stText"] {font-size:1.3rem; font-weight:650; letter-spacing:-.02em}
[class*="st-key-application_card_"] > [data-testid="stElementContainer"]:nth-child(2) [data-testid="stText"] {font-size:1.2rem; font-weight:650}
.st-key-roadmap_guide {padding:1.5rem; border:1px solid #795399; border-top:3px solid #b79aff;
 border-radius:20px; background:radial-gradient(ellipse at 100% 0%,#724ab54d,transparent 70%),#20182f}
.st-key-roadmap_guide h3 {font-size:1.7rem; line-height:1.25}
.st-key-roadmap_progress {padding:1.4rem; background:linear-gradient(110deg,#302044,#20182f);
 border:1px solid #79569a; border-radius:20px}
.st-key-roadmap_metrics [data-testid="stMetric"] {min-height:0; background:#1e162d}
.st-key-roadmap_progress [data-testid="stProgress"] {padding:1rem 0; border:0; background:transparent}
.st-key-milestone_detail {padding:1.3rem; border-left:4px solid #b284ff; background:#241b35; border-radius:16px}
.st-key-interview_workspace [data-testid="stText"] {line-height:1.7; white-space:pre-wrap}
.st-key-interview_question_prompt [data-testid="stText"] {font-size:1.3rem; font-weight:650}
[data-testid="stHorizontalBlock"]:has(h5) [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] {
 padding:1.2rem; background:linear-gradient(145deg,#302044,#1c172e); border:1px solid #795399; border-top:3px solid #a97dff; border-radius:20px}
[data-testid="stBadge"] {font-weight:600}
[data-testid="stProgress"] {padding:1.1rem; background:#1b162d; border:1px solid #70448b; border-radius:14px}
[data-testid="stProgress"] [role="progressbar"] {background:#66347f; border-radius:20px}
[data-testid="stProgress"] [role="progressbar"] > div {background:linear-gradient(90deg,#af67ff,#79baff)}
[data-testid="stDataFrame"], [data-testid="stTable"] {border:1px solid #70448b; border-radius:12px}
[data-testid="stTable"] th {background:#4e2866; color:var(--ai-text)}
[data-testid="stTable"] td {color:var(--ai-text); border-color:#70448b}
[data-testid="stText"] {white-space:pre-wrap; overflow-wrap:anywhere}
[data-testid="stColumn"] {min-width:0}
[data-testid="stChatMessage"], [data-testid="stCode"] {background:#1b162d; border:1px solid #70448b; border-radius:16px}
[data-testid="stBottomBlockContainer"] {background:var(--ai-bg)}
[data-testid="stFileUploaderDropzone"] {background:#1b162d; border:1px dashed #9864ae; border-radius:13px}
[data-testid="stAlert"] {border-radius:12px; border:1px solid #d3a1ff4d}
@media(min-width:641px) and (max-width:1100px) {
 :is(.st-key-application_grid,.st-key-saved_milestone_grid,.st-key-preview_milestone_grid,.st-key-overview) [data-testid="stHorizontalBlock"],
 [data-testid="stHorizontalBlock"]:has(h5) {flex-wrap:wrap}
 :is(.st-key-application_grid,.st-key-saved_milestone_grid,.st-key-preview_milestone_grid,.st-key-overview) [data-testid="stColumn"],
 [data-testid="stHorizontalBlock"]:has(h5) > [data-testid="stColumn"] {flex:1 1 calc(50% - 1rem)!important; min-width:0}
}
@media(max-width:1100px) {
 .st-key-roadmap_studio [data-testid="stHorizontalBlock"] {flex-wrap:wrap}
 .st-key-roadmap_studio [data-testid="stColumn"] {flex:1 1 100%!important; min-width:0}
}
@media(max-width:800px) {
 .st-key-hero_actions [data-testid="stHorizontalBlock"] {flex-wrap:wrap}
 .st-key-hero_actions [data-testid="stColumn"] {flex:1 1 100%!important}
 .st-key-hero_actions [data-testid="stColumn"]:last-child {display:none}
}
@media(max-width:640px) {
 [data-testid="stMainBlockContainer"] {padding:5rem 1rem 2rem}
 [data-testid="stMain"] [data-testid="stHorizontalBlock"] {flex-wrap:wrap}
 [data-testid="stMain"] [data-testid="stColumn"] {min-width:0; flex:1 1 100%}
 .st-key-overview [data-testid="stColumn"] {flex:1 1 calc(50% - 1rem)!important}
 [data-testid="stForm"], .st-key-application_listing, .st-key-roadmap_guide {padding:1rem}
 .st-key-page_intro {padding-bottom:1rem}
 .st-key-dashboard_hero {padding:1.4rem; border-radius:20px}
 .st-key-overview [data-testid="stMetric"] {padding:1rem; min-height:7.5rem}
 [data-testid="stMetric"] {padding:.8rem}
}
@media(prefers-reduced-motion:reduce) {
 .stApp *, .stApp *::before, .stApp *::after {animation:none!important; transition:none!important; scroll-behavior:auto!important}
}
@media(forced-colors:active) {
 .st-key-page_intro h1 {background:none; color:CanvasText}
}
</style>"""


def style_application_table(records):
    """Highlight status without changing displayed values."""
    import pandas as pd

    return pd.DataFrame(records).style.map(
        lambda _: "color: #f0dbff; background-color: #573075; font-weight: 600",
        subset=["Status"],
    )
