"""Shared career workspace theme. Only static CSS; user content uses native widgets."""

DARK_STYLE = """<style>
:root {
 --ai-bg:#090f20; --ai-panel:#1b162d; --ai-border:#795399;
 --ai-text:#faf5ff; --ai-muted:#d5bfe7; --ai-accent:#d3a1ff;
}
.stApp {
 color-scheme:dark; color:var(--ai-text); background-color:var(--ai-bg);
 background-image:radial-gradient(ellipse at 18% 0%,#25457324,transparent 50%),
 radial-gradient(ellipse at 100% 50%,#1b365d18,transparent 50%),
 linear-gradient(135deg,#090f20,#0c1428 60%,#101b32);
}
[data-testid="stHeader"] {
 background:linear-gradient(100deg,#0d162c,#14213b); border-bottom:1px solid #4f366b;
}
[data-testid="stMainBlockContainer"] {max-width:1580px; padding:5rem 2.5rem 3rem}
[data-testid="stSidebar"] {background:linear-gradient(180deg,#111c34,#0b1226 65%); border-right:1px solid #563974}
.st-key-brand {border-bottom:1px solid #70448b; padding-bottom:1.1rem; margin-bottom:.6rem}
.st-key-brand h1 {font-size:1.45rem; letter-spacing:-.045em; font-weight:700}
.st-key-brand h1::before {content:""; display:inline-block; width:.65em; height:.65em; margin-right:.55em;
 border-radius:4px; background:linear-gradient(135deg,#b594ff,#79baff)}
.st-key-brand [data-testid="stCaptionContainer"] {font-size:.68rem; letter-spacing:.12em}
[data-testid="stSidebar"] [role="radiogroup"] {gap:.35rem}
[data-testid="stSidebar"] [role="radiogroup"] > div {width:100%}
[data-testid="stSidebar"] [role="radiogroup"] label {position:relative; display:flex!important;
 flex-direction:row!important; align-items:center; width:100%!important; box-sizing:border-box;
 padding:.85rem .8rem .85rem 2.7rem; min-height:54px; gap:.65rem; border:1px solid transparent; border-radius:12px}
[data-testid="stSidebar"] [role="radiogroup"] label::before {content:"▦"; position:absolute; left:.85rem;
 top:50%; transform:translateY(-50%); line-height:1; font-size:1.25rem; color:#c8a9ff}
[data-testid="stSidebar"] label:has(input[value="1"])::before {content:"⊕"}
[data-testid="stSidebar"] label:has(input[value="2"])::before {content:"◇"}
[data-testid="stSidebar"] label:has(input[value="3"])::before {content:"◈"}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {background:#38244f}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {border-color:#986ecc;
 border-left:4px solid #b189ff; background:linear-gradient(110deg,#503078,#35224d)}
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
.st-key-workspace_bar {border-bottom:1px solid #51336c; padding:.2rem 0 .7rem; margin-bottom:.6rem}
.st-key-workspace_bar [data-testid="stCaptionContainer"] {letter-spacing:.12em; font-size:.72rem}
.st-key-workspace_bar [data-testid="stText"] {font-size:1rem; color:var(--ai-muted)}
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
 background:#482665; color:var(--ai-text); font-weight:550; transition:background-color .12s ease}
[data-testid="stButton"] button:hover, [data-testid="stFormSubmitButton"] button:hover {
 border-color:#d3a1ff; background:#67368a; color:#fff}
button[kind^="primary"], [data-testid="stBaseButton-primary"] {
 background:linear-gradient(110deg,#773cf0,#9549e9)!important;
 border:1px solid #db94f5!important; color:#fff!important; box-shadow:0 4px 14px #773cf033}
button[kind^="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
 background:linear-gradient(110deg,#6630cf,#7e36c7)!important}
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
[data-testid="stMetric"] {min-width:0; min-height:8rem; padding:1.1rem; border:1px solid #75519b;
 border-radius:18px; background:linear-gradient(125deg,#342249,#241a37)}
[data-testid="stMetricLabel"] p {color:var(--ai-muted); white-space:normal; line-height:1.5}
[data-testid="stMetricValue"] {font-variant-numeric:tabular-nums; letter-spacing:-.045em; color:var(--ai-text)}
[data-testid="stMetricValue"] > div {font-size:clamp(1.4rem,2.3vw,2rem); white-space:normal; overflow-wrap:anywhere}
.st-key-overview {margin:.4rem 0 1rem}
.st-key-application_listing {padding:1.4rem; background:#171225; border:1px solid #5f3e7c; border-radius:22px}
.st-key-application_summary {padding:1.1rem; background:#1c152e; border:1px solid #634283; border-radius:20px}
.st-key-application_summary [data-testid="stMetric"] {min-height:0; padding:.9rem}
[class*="st-key-application_card_"], .st-key-interview_question_card, .st-key-interview_answer_card,
[class*="st-key-saved_milestone_card_"], [class*="st-key-preview_milestone_card_"] {
 padding:1.2rem; background:linear-gradient(145deg,#2b203d,#1c172e); border:1px solid #795399; border-radius:20px}
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
@media(max-width:640px) {
 [data-testid="stMainBlockContainer"] {padding:5rem 1rem 2rem}
 [data-testid="stMain"] [data-testid="stHorizontalBlock"] {flex-wrap:wrap}
 [data-testid="stMain"] [data-testid="stColumn"] {min-width:0; flex:1 1 100%}
 .st-key-overview [data-testid="stColumn"] {flex:1 1 calc(50% - 1rem)!important}
 [data-testid="stForm"], .st-key-application_listing, .st-key-roadmap_guide {padding:1rem}
 .st-key-page_intro {padding-bottom:1rem}
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
