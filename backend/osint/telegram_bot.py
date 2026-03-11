#!/usr/bin/env python3
"""
Herkulio Intelligence Bot v8
Brain + Identity + Memory + Skills + Tools + Menu + Learner
"""
import os, sys, json, time, threading, re, logging
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
# Persistent rotating logs
sys.path.insert(0, os.path.dirname(__file__))
try:
    from logging_config import setup as _setup_logging; _setup_logging()
except: pass
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agent"))
import identity as ID
import memory   as MEM

# Import tools module directly to avoid conflict with tools/ directory
import importlib.util
spec = importlib.util.spec_from_file_location("tools", os.path.join(os.path.dirname(__file__), "agent", "tools.py"))
tools_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools_module)
TOOLS = tools_module

import brain    as BRAIN
import skills   as SKILLS
import menu     as MENU
import learner   as LEARNER
import protocols as PROTOCOLS
import intake    as INTAKE
import router    as ROUTER
import wizard       as WIZARD
import followup     as FOLLOWUP
import model_router as MR
import userdb       as USERDB
import db           as HDB
# Delay dispatcher import until after TOOL_MAP is available
build_search_plan = None
format_plan_summary = None
import onboarding   as ONBOARD
import admin        as ADMIN
import sys as _sys; _sys.path.insert(0,'/home/jarvis/.openclaw/workspace/osint/pdf_engine')
import generator as PDF_GEN
import resolver  as RESOLVER
import casefile  as CASEFILE

BOT_TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN", "8681870646:AAHGlpY-mQfTjKefIQdtJ-lGtfAh6tTN6kU")
ARCHIVE_CHANNEL = os.environ.get("ARCHIVE_CHANNEL", "-1003850622505")
REPORTS_DIR     = os.path.join(os.path.dirname(__file__), "reports")
OSINT_PARENT    = os.path.dirname(__file__)   # /osint/ — for new engine modules

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# RUNNING is now DB-backed (crash-safe) — see agent/db.py
HDB.clear_stale_locks()  # clear any locks from previous crash

# ── System prompt — rebuilt daily, includes learned context ──────────────────
_sys_cache = {"prompt": None, "date": None}

def get_system(user_id: int) -> str:
    today = time.strftime("%Y-%m-%d")
    if _sys_cache["date"] != today or not _sys_cache["prompt"]:
        base = ID.build_system_prompt() + SKILLS.get_active_rules()
        _sys_cache["prompt"] = base
        _sys_cache["date"]   = today
    learned  = LEARNER.get_learned_context()
    session  = MEM.get_context_summary(user_id)
    extra    = ("\n\n## WHAT I'VE LEARNED\n" + learned) if learned else ""
    return _sys_cache["prompt"] + extra + session

# ── Telegram helpers ──────────────────────────────────────────────────────────
def tg(method, **params):
    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(params).encode()
    req  = urllib.request.Request(url, data=data,
                                   headers={"Content-Type":"application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read())
    except Exception as e:
        log.error(f"TG {method}: {e}"); return {}

def send(chat_id, text, buttons=None):
    text = str(text)
    # Telegram hard limit is 4096 chars — split into chunks
    chunks = [text[i:i+4000] for i in range(0, max(1, len(text)), 4000)]
    result = None
    for idx, chunk in enumerate(chunks):
        is_last = (idx == len(chunks) - 1)
        params = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
        if buttons and is_last:
            params["reply_markup"] = json.dumps({"inline_keyboard": [
                [{"text": l, "callback_data": c} for l, c in row] for row in buttons
            ]})
        result = tg("sendMessage", **params)
    return result

def send_long(chat_id, text):
    for chunk in [str(text)[i:i+3800] for i in range(0, len(str(text)), 3800)]:
        send(chat_id, chunk); time.sleep(0.3)

def typing(chat_id):
    tg("sendChatAction", chat_id=chat_id, action="typing")

def del_msg(chat_id, mid):
    tg("deleteMessage", chat_id=chat_id, message_id=mid)

def answer_cb(cb_id, text=""):
    tg("answerCallbackQuery", callback_query_id=cb_id, text=text)

def archive_text(text: str, label: str = ""):
    header = f"[{time.strftime('%Y-%m-%d %H:%M')} ET]{' — '+label if label else ''}\n\n"
    for chunk in [str(text)[i:i+3800] for i in range(0, len(str(text)), 3800)]:
        tg("sendMessage", chat_id=ARCHIVE_CHANNEL,
           text=header+chunk, disable_web_page_preview=True)
        time.sleep(0.3)

# ── Report formatter ──────────────────────────────────────────────────────────
def format_report(osint_result: dict, narrative: str) -> str:
    r = osint_result.get("report", {}) if isinstance(osint_result, dict) else {}
    if not r: return narrative
    risk    = r.get("risk_rating", "UNKNOWN")
    r_label = {"HIGH":"🔴 HIGH RISK","MEDIUM":"🟡 MEDIUM RISK","LOW":"🟢 LOW RISK"}.get(risk, f"⚪ {risk}")
    target  = r.get("target", "—")
    L = [
        "╔══════════════════════════════╗",
        "      HERKULIO INTELLIGENCE",
        "        CLASSIFIED REPORT",
        "╚══════════════════════════════╝",
        f"TARGET : {target}",
        f"RISK   : {r_label}",
        "──────────────────────────────", "",
    ]
    if narrative:
        L += ["🧠 ANALYST ASSESSMENT", "", narrative[:2000], "", "──────────────────────────────", ""]
    if r.get("key_facts"):
        L += ["🔑 KEY FACTS"]
        for f in r["key_facts"][:8]: L.append(f"  • {f}")
        L.append("")
    cr = r.get("corporate_records",{})
    if isinstance(cr,dict) and any(cr.values()):
        L += ["🏢 CORPORATE RECORDS"]
        for k in ["legal_name","status","registration_number","ein_fein",
                  "incorporation_date","principal_address","registered_agent"]:
            if cr.get(k): L.append(f"  {k.replace('_',' ').title()}: {cr[k]}")
        L.append("")
    if r.get("people"):
        L += ["👤 PEOPLE"]
        for p in r["people"][:5]:
            if isinstance(p,dict):
                ln = f"  • {p.get('name','')}"
                if p.get("role"):  ln += f" — {p['role']}"
                if p.get("email"): ln += f" | {p['email']}"
                if p.get("phone"): ln += f" | {p['phone']}"
                L.append(ln)
            else: L.append(f"  • {p}")
        L.append("")
    if r.get("red_flags"):
        L += [f"🚩 RED FLAGS ({len(r['red_flags'])})"]
        for f in r["red_flags"][:10]: L.append(f"  • {f}")
        L.append("")
    if r.get("green_flags"):
        L += [f"✅ GREEN FLAGS ({len(r['green_flags'])})"]
        for f in r["green_flags"][:6]: L.append(f"  • {f}")
        L.append("")
    L += ["🔐 COMPLIANCE"]
    ofac = r.get("ofac_status",{})
    L.append(f"  OFAC/SDN:   {'✅ CLEAR' if isinstance(ofac,dict) and ofac.get('status')=='CLEAR' else '🚨 CHECK'}")
    icij = r.get("icij_offshore",{})
    L.append(f"  ICIJ Leaks: {'⚠️  HIT' if isinstance(icij,dict) and icij.get('found') else '✅ CLEAR'}")
    bk   = r.get("bankruptcy",{})
    L.append(f"  Bankruptcy: {'⚠️  Found' if isinstance(bk,dict) and bk.get('found') else '✅ None'}")
    L.append("")
    wpp = r.get("watch_platform_presence",{})
    if isinstance(wpp,dict) and any(wpp.values()):
        L += ["⌚ MARKETPLACE"]
        for k,v in wpp.items():
            if v: L.append(f"  {k.title()}: {v}")
        L.append("")
    if r.get("data_gaps"):
        L += ["⚠️  DATA GAPS"]
        for g in r["data_gaps"][:4]: L.append(f"  • {g}")
        L.append("")
    meta = r.get("_meta",{})
    cost = meta.get("total_cost_usd")
    srcs = len(r.get("sources",[]))
    L += ["──────────────────────────────",
          f"Sources: {srcs}" + (f" | Cost: ${cost:.4f}" if cost else ""),
          "──────────────────────────────"]
    return "\n".join(L)

# ── Archive dump — pulls everything from current session into archive ─────────
def cmd_archive_dump(chat_id, user_id):
    """Generate CIA dossier PDF and send + archive it."""
    history     = MEM.get_history(user_id)
    researched  = MEM.get_researched(user_id)
    proto_params = MEM.get_meta(user_id, "protocol_params") or {}

    if not history:
        send(chat_id, "Nothing to archive yet. Run a search first."); return

    # Determine target
    target_name = proto_params.get("name") or proto_params.get("target","Unknown Subject")
    entity_type = (proto_params.get("entity_type") or "entity").upper()

    # Find the most complete intelligence brief in history
    brief_text = ""
    for turn in reversed(history):
        if turn.get("role") == "assistant" and len(turn.get("content","")) > 400:
            brief_text = turn["content"]
            break

    if not brief_text and researched:
        brief_text = "\n".join([
            f"[{t.get('risk','?')} RISK] {t['target']} — {t.get('ts','')}"
            for t in researched
        ])

    if not brief_text:
        send(chat_id, "No intelligence brief found in this session yet."); return

    send(chat_id, f"Generating CIA dossier PDF for {target_name}...")

    try:
        pdf_path     = PDF_GEN.generate_pdf(target_name, brief_text, entity_type, proto_params)
        file_size_kb = os.path.getsize(pdf_path) // 1024
        fname        = os.path.basename(pdf_path)

        caption = (
            f"HERKULIO INTELLIGENCE DOSSIER\n"
            f"Subject:   {target_name}\n"
            f"Type:      {entity_type}\n"
            f"Generated: {time.strftime('%Y-%m-%d %H:%M')} ET\n"
            f"File:      {file_size_kb}KB\n\n"
            f"All data from publicly available sources only.\n"
            f"Not for FCRA-regulated use."
        )

        # Send to user
        with open(pdf_path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (fname, f, "application/pdf")},
                timeout=60
            )

        # Mirror to archive channel
        with open(pdf_path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={"chat_id": ARCHIVE_CHANNEL, "caption": f"ARCHIVED — {caption}"},
                files={"document": (fname, f, "application/pdf")},
                timeout=60
            )

        send(chat_id, f"Dossier sent. {file_size_kb}KB — also mirrored to Intelligence Archive.")
        log.info(f"PDF dossier generated and archived: {fname}")

    except Exception as e:
        log.error(f"PDF failed: {e}")
        # Fallback: text dump
        dump_lines = [
            f"ARIA SESSION DUMP — {target_name}",
            f"Date: {time.strftime('%Y-%m-%d %H:%M')} ET",
            "", brief_text[:3500]
        ]
        archive_text("\n".join(dump_lines), "FALLBACK DUMP")
        send(chat_id, f"PDF error ({str(e)[:80]}) — text dump sent to archive instead.")
    mid = wait.get("result",{}).get("message_id")
    if mid: del_msg(chat_id, mid)
    send(chat_id, f"✅ Session archived to Intelligence Archive.\n{len(researched)} targets, {len(history)} turns.",
         buttons=[[("🔍 New search","back_main"),("📁 View recent","recent")]])

# ── Main conversation handler ─────────────────────────────────────────────────

def _extract_protocol_params(text: str, proto_type: str) -> dict:
    """
    Parse user's target text into structured protocol params.
    e.g. "Gerald Librati Montreal QC watch dealer" → {name, city, state, notes}
    """
    import re
    params = {}
    t = text.strip()

    # Extract email
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', t)
    if email_match:
        params["email"] = email_match.group(0)

    # Extract phone
    phone_match = re.search(r'\+?[\d][\d\s\-\.\(\)]{7,}[\d]', t)
    if phone_match:
        params["phone"] = phone_match.group(0)

    # Extract URL
    url_match = re.search(r'https?://[\S]+', t)
    if url_match:
        params["url"] = url_match.group(0)

    # Extract domain (if domain protocol)
    if proto_type == "domain":
        domain_match = re.search(r'(?:https?://)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', t)
        if domain_match:
            params["domain"] = domain_match.group(1)
            if not params.get("url"): params["url"] = f"https://{params['domain']}"
        return params

    # Extract @handle
    handle_match = re.search(r'@([\w.]+)', t)
    if handle_match:
        params["handle"] = handle_match.group(1)

    if proto_type == "username":
        params["username"] = params.get("handle") or t.lstrip("@").split()[0]
        return params

    if proto_type in ("email",) and params.get("email"):
        return params

    if proto_type in ("phone",) and params.get("phone"):
        return params

    # State detection
    state_map = {
        "FL": "FL", "florida": "FL", "Miami": "FL", "Orlando": "FL", "Tampa": "FL",
        "NY": "NY", "new york": "NY", "CA": "CA", "california": "CA",
        "QC": "QC", "Quebec": "QC", "Montreal": "QC", "Laval": "QC",
        "ON": "ON", "Ontario": "ON", "Toronto": "ON",
        "TX": "TX", "Texas": "TX", "NV": "NV", "Nevada": "NV",
    }
    detected_state = ""
    for keyword, code in state_map.items():
        if keyword.lower() in t.lower():
            detected_state = code
            break

    # Country detection
    country = "US"
    if any(k in t.lower() for k in ["canada", "montreal", "toronto", "qc", "ontario", "bc", "alberta"]):
        country = "CA"
    elif any(k in t.lower() for k in ["uk", "london", "england", "switzerland", "geneva", "uae", "dubai"]):
        country = "INTL"

    # City detection (rough)
    cities = ["Miami","New York","Los Angeles","Chicago","Houston","Montreal","Toronto",
              "Laval","Westmount","Boca Raton","Fort Lauderdale","Aventura","Sunny Isles",
              "CSL","TMR","Côte Saint-Luc","Town of Mount Royal","Geneva","London","Dubai"]
    detected_city = ""
    for city in cities:
        if city.lower() in t.lower():
            detected_city = city
            break

    # Name extraction: take first 2-4 words, strip known location/noise words
    noise = {"LLC","Inc","Corp","Ltd","Group","Holdings","the","and","or","of","for","in","at"}
    words = t.split()
    name_words = []
    for w in words[:5]:
        if w.strip(",").strip() not in noise and not re.match(r'^\+?\d', w):
            name_words.append(w.strip(","))
        if len(name_words) >= 4:
            break
    name = " ".join(name_words)

    params.update({
        "name":    name,
        "target":  name,
        "state":   detected_state,
        "city":    detected_city,
        "country": country,
        "notes":   t,  # pass full text as notes for extra context
    })
    return params

def handle(chat_id, user_id, text):
    if HDB.is_running(user_id):
        send(chat_id, "⏳ Search already running — stand by..."); return

    # Check for learning signals
    sig_type, sig_content = LEARNER.detect_learning_signal(text)
    if sig_type == "correction":
        LEARNER.log_correction(
            user_said=text,
            old_behavior="previous behavior",
            new_behavior=f"User instructed: {text}"
        )

    # Rate limiting — max 12 messages/min, 3 searches/min
    rate_ok, retry_in = HDB.check_rate(user_id, is_search=False)
    if not rate_ok:
        send(chat_id, f"⏳ Slow down — try again in {retry_in}s."); return

    MEM.add_turn(user_id, "user", text)
    history = MEM.get_history(user_id)
    system  = get_system(user_id)
    # Search rate limit (3 searches/min max)
    search_rate_ok, search_retry = HDB.check_rate(user_id, is_search=True)
    if not search_rate_ok:
        send(chat_id, f"⏳ Search rate limit — wait {search_retry}s before next search."); return

    # Check search quota
    allowed, reason = USERDB.can_search(user_id)
    if not allowed:
        send(chat_id, reason, buttons=[[("💳 Upgrade Plan","upgrade_info")]]); return

    HDB.mark_running(user_id)

    # ── CONVERSATIONAL MODE: detect if this is a follow-up or new search ──────
    active_inv = MEM.get_active_investigation(user_id)
    has_active = bool(active_inv and active_inv.get("target"))

    from intake import detect_message_intent
    msg_intent = detect_message_intent(text, has_active)

    if msg_intent == "chat":
        # Pure conversational — respond naturally using session context, no tools
        def run_chat():
            try:
                typing(chat_id)
                MEM.add_turn(user_id, "user", text)
                reply = BRAIN.think(MEM.get_history(user_id), system, max_tokens=800)
                MEM.add_turn(user_id, "assistant", reply)
                send_long(chat_id, reply)
            except Exception as e:
                send(chat_id, f"Error: {e}")
            finally:
                HDB.mark_done(user_id)
        threading.Thread(target=run_chat, daemon=True).start()
        return

    if msg_intent == "followup" and has_active:
        # Follow-up on current investigation — use brain with full context, selectively fire tools
        def run_followup():
            try:
                typing(chat_id)
                active_target = active_inv.get("target", "")
                active_params = active_inv.get("params", {})
                entity_profile = MEM.get_meta(user_id, "last_entity_profile") or {}

                # Build context-rich prompt
                context_summary = f"""You are a deep intelligence analyst. The user is currently investigating: {active_target}

Known profile so far:
{entity_profile.get('summary', 'See conversation history above')}

The user is now asking: {text}

Use the investigation history and known facts to answer. If you need to run additional targeted searches to answer this specific question, call the appropriate tool with precise parameters. Otherwise answer directly from what's already known. Be specific and direct."""

                MEM.add_turn(user_id, "user", context_summary)
                reply = BRAIN.think(MEM.get_history(user_id), system, max_tokens=2000)

                # Check if brain wants to call tools
                tool_calls = TOOLS.extract_tool_calls(reply)
                if tool_calls:
                    display = reply
                    for _, _, raw in tool_calls: display = display.replace(raw, "").strip()
                    if display: send_long(chat_id, display)

                    all_results = {}
                    _std_calls = [(tn, p, tn, tn) for tn, p, _ in tool_calls]
                    wait = tg("sendMessage", chat_id=chat_id,
                              text=f"🔍 Running {len(_std_calls)} targeted searches...")
                    try:
                        from parallel import run_tools_parallel as _run_par
                        _par_res = _run_par(_std_calls, config={}, max_workers=8, timeout=60)
                        for tn, p, _ in tool_calls:
                            all_results[tn] = _par_res.get(tn, {"status":"timeout"})
                    except Exception as _pe:
                        for tn, p, _ in tool_calls:
                            all_results[tn] = TOOLS.run_tool(tn, p)
                    mid = wait.get("result",{}).get("message_id")
                    if mid: del_msg(chat_id, mid)

                    results_text = BRAIN.format_tool_results(all_results)
                    MEM.add_turn(user_id, "assistant", reply)
                    MEM.add_turn(user_id, "user", f"Search results: {results_text[:3000]}")
                    final = BRAIN.think(MEM.get_history(user_id), system, max_tokens=2000)
                    MEM.add_turn(user_id, "assistant", final)
                    send_long(chat_id, final)
                else:
                    MEM.add_turn(user_id, "assistant", reply)
                    send_long(chat_id, reply)

                # Keep follow-up buttons
                risk_val = entity_profile.get("risk_rating","UNKNOWN")
                entity_type = active_params.get("entity_type","person")
                buttons = MENU.post_report_buttons(risk_val, bool(entity_profile.get("red_flags")), active_target, entity_type)
                send(chat_id, "What else do you want to know?", buttons=buttons)
            except Exception as e:
                log.error(f"Followup error: {e}", exc_info=True)
                send(chat_id, f"Error: {e}")
            finally:
                HDB.mark_done(user_id)
        threading.Thread(target=run_followup, daemon=True).start()
        return

    # ── Detect protocol from session context ──────────────────────────────────
    pending_proto = MEM.get_meta(user_id, "pending_protocol")
    awaiting_clarification = MEM.get_meta(user_id, "awaiting_clarification")

    if awaiting_clarification:
        # User answered our clarification question — merge answer into pending params
        pending_proto = awaiting_clarification
        MEM.set_meta(user_id, "awaiting_clarification", None)

    if pending_proto:
        # Smart intake: parse with full context awareness
        active_ctx = MEM.get_active_investigation(user_id).get("params", {})
        proto_params = INTAKE.parse_intake(text, proto_hint=pending_proto, active_context=active_ctx)
        proto_type   = pending_proto

        # Check if we need clarification before firing
        needs_q, question = INTAKE.needs_clarification(proto_params)
        if needs_q and not awaiting_clarification:
            # Ask one focused question, then wait
            MEM.set_meta(user_id, "awaiting_clarification", pending_proto)
            MEM.set_meta(user_id, "pending_protocol", None)
            send(chat_id, question, buttons=[[("Skip — search anyway", f"skip_clarify:{pending_proto}:{text[:50]}")]])
            HDB.mark_done(user_id)
            return

        # Smart jurisdiction-aware dispatch
        try:
            # Lazy import to avoid circular dependency
            import sys as _dsp_sys; _dsp_sys.path.insert(0, '/home/jarvis/.openclaw/workspace/osint/agent')
            from sources.dispatcher import build_search_plan as _bsp
            search_plan = _bsp(proto_params)
            proto_params["_search_plan"] = search_plan
            proto_params["_jurisdictions"] = search_plan["jurisdictions"]
            # Override entity type from dispatcher detection
            if not proto_params.get("entity_type") or proto_params["entity_type"] == "unknown":
                proto_params["entity_type"] = search_plan["entity_type"]
        except Exception as e:
            log.debug(f"Dispatcher error (non-fatal): {e}")

        MEM.set_meta(user_id, "active_protocol",  proto_type)
        MEM.set_meta(user_id, "protocol_params",  proto_params)
        MEM.set_meta(user_id, "pending_protocol", None)
    else:
        proto_type   = MEM.get_meta(user_id, "active_protocol")
        proto_params = MEM.get_meta(user_id, "protocol_params") or {}

    def run():
        try:
            typing(chat_id)

            # ── PROTOCOL MODE: fire predefined tool sequence directly ──────
            if proto_type and proto_params:
                protocol_calls = ROUTER.build_adaptive_route(proto_type, proto_params, prior_profile=MEM.get_active_investigation(user_id).get('params'))
                MEM.set_meta(user_id, "active_protocol", None)
                MEM.set_meta(user_id, "protocol_params", None)

                if protocol_calls:
                    summary = PROTOCOLS.PROTOCOL_SUMMARIES.get(proto_type, f"{proto_type.upper()} SEARCH")
                    wait_msg = tg("sendMessage", chat_id=chat_id,
                                   text=f"{summary}\n\nFiring {len(protocol_calls)} search vectors...\nStand by.",
                                   disable_web_page_preview=True)
                    all_results = {}
                    _t_start = time.time()
                    try:
                        # ── PARALLEL EXECUTION ────────────────────────────────
                        import sys as _par_sys; _par_sys.path.insert(0, '/home/jarvis/.openclaw/workspace/osint/agent')
                        from parallel import run_tools_parallel
                        # Convert protocol_calls to (tool_name, params, src_id, label) tuples
                        _par_calls = [
                            (tool_name, params, f"{tool_name}_{i}", _tool_label(tool_name, params))
                            for i, (tool_name, params) in enumerate(protocol_calls, 1)
                        ]
                        _par_results = run_tools_parallel(_par_calls, config={}, max_workers=10, timeout=120)
                        # Map back to original keyed format
                        for i, (tool_name, params) in enumerate(protocol_calls, 1):
                            key    = f"{tool_name}_{i}"
                            result = _par_results.get(tool_name, _par_results.get(key, {"status":"timeout"}))
                            if isinstance(result, dict) and result.get("error"):
                                LEARNER.log_roadblock(str(params), tool_name, result["error"])
                            all_results[key] = result
                        _elapsed = round(time.time() - _t_start, 1)
                        log.info(f"Parallel: {len(protocol_calls)} tools in {_elapsed}s")
                    except Exception as _par_err:
                        log.warning(f"Parallel execution failed ({_par_err}), falling back to sequential")
                        for i, (tool_name, params) in enumerate(protocol_calls, 1):
                            label = _tool_label(tool_name, params)
                            log.info(f"  [{i}/{len(protocol_calls)}] {label}")
                            result = TOOLS.run_tool(tool_name, params)
                            if isinstance(result, dict) and result.get("error"):
                                LEARNER.log_roadblock(str(params), tool_name, result["error"])
                            all_results[f"{tool_name}_{i}"] = result

                    wait_mid = wait_msg.get("result",{}).get("message_id")
                    if wait_mid: del_msg(chat_id, wait_mid)

                    # ── SIGNAL FILTER: prune empties, dedup, gate sections ──
                    import sys as _sf_sys; _sf_sys.path.insert(0, '/home/jarvis/.openclaw/workspace/osint/agent')
                    try:
                        import filter as FILTER
                        entity_type_for_filter = proto_params.get("entity_type", proto_params.get("type",""))
                        filter_out   = FILTER.run_pipeline(all_results, entity_type_for_filter)
                        all_results  = filter_out["results"]   # clean signal only
                        active_sections = filter_out["sections"]
                        noise_dropped   = filter_out["noise_dropped"]
                        if noise_dropped > 0:
                            log.info(f"Filter: dropped {noise_dropped} empty/duplicate results, {filter_out['signal_count']} signals remain")
                        # ── Normalize all results to standard schema ──────────
                        try:
                            import normalize as NORM
                            all_results = NORM.normalize_all(all_results)
                        except Exception as _ne:
                            log.warning(f"Normalize error (non-fatal): {_ne}")
                    except Exception as _fe:
                        log.warning(f"Filter pipeline error (non-fatal): {_fe}")
                        active_sections = {}

                    # Synthesize all results
                    typing(chat_id)
                    results_text = BRAIN.format_tool_results(all_results)
                    target_for_synth = proto_params.get("name") or proto_params.get("target","unknown")

                    # ── ENTITY RESOLVER: deduplicate, merge, detect conflicts ──
                    entity_profile  = RESOLVER.build_entity_profile(target_for_synth, all_results)
                    ranked_results  = RESOLVER.rank_results(all_results)
                    resolved_context = RESOLVER.format_for_synthesis(entity_profile, ranked_results)

                    # Log any conflicts detected
                    if entity_profile.get("conflicts"):
                        for c in entity_profile["conflicts"]:
                            log.info(f"Conflict detected: {c['field']} — {c['note']}")

                    # ── PATTERN DETECTOR: fraud/behavioral pattern analysis ──
                    patterns_detected = []
                    try:
                        import sys as _pd_sys; _pd_sys.path.insert(0, OSINT_PARENT)
                        from pattern_detector import PatternDetector, format_pattern_results
                        pd = PatternDetector()
                        patterns_detected = pd.analyze(entity_profile, all_results, proto_params)
                        if patterns_detected:
                            log.info(f"Patterns detected: {[p.get('name') for p in patterns_detected]}")
                    except Exception as _pde:
                        log.debug(f"Pattern detector (non-fatal): {_pde}")

                    # ── INVESTIGATION MEMORY: store + check prior knowledge ──
                    prior_hits = []
                    try:
                        import sys as _im_sys; _im_sys.path.insert(0, OSINT_PARENT)
                        from investigation_memory import store_investigation, check_prior_knowledge
                        prior_hits = check_prior_knowledge(entity_profile)
                        if prior_hits:
                            log.info(f"Prior knowledge hits: {len(prior_hits)} entity matches")
                    except Exception as _ime:
                        log.debug(f"Investigation memory (non-fatal): {_ime}")

                    synth_prompt = BRAIN.build_adaptive_synthesis(
                        resolved_context, target_for_synth, entity_profile,
                        active_sections=active_sections,
                        industry=proto_params.get("industry",""))
                    MEM.add_turn(user_id, "user", synth_prompt)
                    final = BRAIN.think(MEM.get_history(user_id), system, max_tokens=4000)

                    # Store resolved profile in session for follow-up commands
                    MEM.set_meta(user_id, "last_entity_profile", entity_profile)
                    MEM.add_turn(user_id, "assistant", final)

                    # Find primary OSINT result for formatting
                    osint_result = {}
                    for k, v in all_results.items():
                        if "TOOL_OSINT" in k and isinstance(v, dict) and v.get("report"):
                            osint_result = v; break

                    report_data  = osint_result.get("report", {}) if osint_result else {}
                    target_name  = proto_params.get("name") or proto_params.get("target","")
                    risk_val     = report_data.get("risk_rating","UNKNOWN")

                    if report_data:
                        full_report = format_report(osint_result, final)
                        MEM.log_target(user_id, target_name, risk_val)
                        MEM.set_active_investigation(user_id, target_name, proto_params)
                        # Record to user database
                        try:
                            USERDB.record_search(user_id, target_name,
                                entity_profile.get("entity_type", proto_params.get("entity_type","")),
                                risk_val, entity_profile.get("confidence",""),
                                reply[:5000], proto_params)
                        except Exception as e:
                            log.debug(f"DB record error: {e}")
                        # Generate follow-up buttons
                        try:
                            fu_msg = FOLLOWUP.build_followup_message(
                                entity_profile, proto_params, reply, target_name)
                            send(chat_id, fu_msg["text"], buttons=fu_msg["buttons"])
                        except Exception as e:
                            log.debug(f"Follow-up error: {e}")
                        # Save to case DB
                        CASEFILE.save_case(
                            target       = target_name,
                            entity_type  = proto_type or "unknown",
                            risk_rating  = risk_val,
                            confidence   = entity_profile.get("confidence","LOW"),
                            report_text  = full_report,
                            entity_profile = entity_profile,
                            protocol_used  = proto_type or "",
                            vectors_fired  = len(protocol_calls),
                        )
                        # Store to investigation memory graph
                        try:
                            from investigation_memory import store_investigation
                            store_investigation(target_name, entity_profile, risk_val, proto_params)
                            log.debug(f"Investigation stored to memory graph: {target_name}")
                        except Exception as _ims:
                            log.debug(f"Memory store (non-fatal): {_ims}")
                        send_long(chat_id, full_report)
                        archive_text(full_report, target_name)
                    else:
                        send_long(chat_id, final)
                        archive_text(final, target_name or proto_type)

                    time.sleep(0.5)
                    entity_type = "company" if proto_type == "company" else "person"
                    buttons = MENU.post_report_buttons(risk_val, bool(report_data.get("red_flags")), target_name, entity_type)
                    send(chat_id, "Protocol complete. What do you want to dig into next?", buttons=buttons)
                    return

            # ── STANDARD MODE: let brain decide which tools to call ────────
            reply = BRAIN.think(history, system)
            log.info(f"Brain: {reply[:100]}")

            tool_calls = TOOLS.extract_tool_calls(reply)

            if not tool_calls:
                MEM.add_turn(user_id, "assistant", reply)
                send_long(chat_id, reply)
                return

            # Strip tool calls, show any preamble
            display = reply
            for _, _, raw in tool_calls: display = display.replace(raw, "").strip()
            if display: send_long(chat_id, display)

            # Execute tools
            all_results = {}
            for tool_name, params, _ in tool_calls:
                labels = {
                    "TOOL_OSINT":     f"🔍 OSINT: {params.get('target','?')} ({params.get('depth','standard').upper()})",
                    "TOOL_SEARCH":    f"🔎 Search: {params.get('query','')[:50]}",
                    "TOOL_INSTAGRAM": f"📸 Instagram: @{params.get('handle','?')}",
                    "TOOL_WHOIS":     f"🌐 WHOIS: {params.get('domain','?')}",
                    "TOOL_PHONE":     f"📱 Phone: {params.get('phone','?')}",
                    "TOOL_EMAIL":     f"📧 Email: {params.get('email','?')}",
                    "TOOL_WAYBACK":   f"⏮ Wayback: {params.get('url','?')}",
                    "TOOL_COMPANY":   f"🏢 Company: {params.get('name','?')}",
                    "TOOL_SANCTIONS":      f"🔐 Sanctions: {params.get('name','?')}",
                    "TOOL_SHERLOCK":       f"👤 Username: {params.get('username','?')}",
                    "TOOL_DDG":            f"🔎 DuckDuckGo: {params.get('query','')[:40]}",
                    "TOOL_DNS":            f"🌐 DNS Intel: {params.get('domain','?')}",
                    "TOOL_SOCID":          f"🔗 Social IDs: {params.get('url','?')[:40]}",
                    "TOOL_SCRAPE":         f"🕷 Scraping: {params.get('url','?')[:40]}",
                    "TOOL_SCRAPE_PW":      f"🛡 CF Bypass: {params.get('url','?')[:40]}",
                    "TOOL_EXPAND_NETWORK": f"🕸 Network expand: {params.get('company','?')} — {len(params.get('people',[]))} principals",
                    "TOOL_PASTE_SEARCH":   f"📋 Paste search: {params.get('query','?')[:40]}",
                    "TOOL_PEOPLE_SEARCH":  f"👥 People search: {params.get('name','?')}",
                    "TOOL_COURTS":         f"⚖️  Court records: {params.get('name','?')}",
                    "TOOL_REQ_QUEBEC":     f"🍁 REQ Quebec: {params.get('name','?')}",
                    "TOOL_SUNBIZ_PW":      f"🌴 Sunbiz FL: {params.get('name','?')}",
                    "TOOL_LINKEDIN":       f"💼 LinkedIn: {params.get('name','?')}",
                    "TOOL_GMAPS":          f"📍 Google Maps: {params.get('query','?')}",
                    "TOOL_COURTLISTENER":  f"⚖️  CourtListener: {params.get('name','?')}",
                }
                # Run all standard-mode tools in parallel too
                _std_calls = [(tn, p, tn, labels.get(tn, tn)) for tn, p, _ in tool_calls]
                wait = tg("sendMessage", chat_id=chat_id,
                          text=f"Running {len(_std_calls)} search vectors in parallel...\n\nStand by.")
                try:
                    from parallel import run_tools_parallel as _run_par
                    _par_res = _run_par(_std_calls, config={}, max_workers=10, timeout=90)
                    for tn, p, _ in tool_calls:
                        result = _par_res.get(tn, {"status":"timeout"})
                        if isinstance(result, dict) and result.get("error"):
                            LEARNER.log_roadblock(str(p), tn, result["error"])
                        all_results[tn] = result
                except Exception as _pe2:
                    log.warning(f"Parallel fallback: {_pe2}")
                    for tn, p, _ in tool_calls:
                        result = TOOLS.run_tool(tn, p)
                        if isinstance(result, dict) and result.get("error"):
                            LEARNER.log_roadblock(str(p), tn, result["error"])
                        all_results[tn] = result
                mid = wait.get("result",{}).get("message_id")
                if mid: del_msg(chat_id, mid)

            # Synthesize
            typing(chat_id)
            osint_result = all_results.get("TOOL_OSINT", {})
            report_data  = osint_result.get("report", {}) if isinstance(osint_result, dict) else {}

            target_name = report_data.get("target","")
            if not target_name:
                for _, params, _ in tool_calls:
                    target_name = (params.get("target") or params.get("name") or
                                   params.get("handle") or params.get("domain",""))
                    if target_name: break

            # Run resolver on standard searches too
            entity_profile   = RESOLVER.build_entity_profile(target_name or "unknown", all_results)
            ranked_results   = RESOLVER.rank_results(all_results)
            resolved_context = RESOLVER.format_for_synthesis(entity_profile, ranked_results)

            MEM.add_turn(user_id, "assistant", reply)
            MEM.add_turn(user_id, "user", f"Resolved results:\n{resolved_context[:4000]}")
            MEM.set_meta(user_id, "last_entity_profile", entity_profile)

            final = BRAIN.think(MEM.get_history(user_id), system, max_tokens=2500)
            MEM.add_turn(user_id, "assistant", final)

            # Format + send
            if report_data:
                risk_val    = report_data.get("risk_rating","UNKNOWN")
                full_report = format_report(osint_result, final)
                MEM.log_target(user_id, target_name, risk_val)
                send_long(chat_id, full_report)
                archive_text(full_report, target_name)
                # Post-report contextual buttons
                time.sleep(0.5)
                entity_type = "company" if any(k in target_name.lower()
                    for k in ["llc","inc","corp","group","gallery"]) else "person"
                followup_buttons = MENU.post_report_buttons(
                    risk_val, bool(report_data.get("red_flags")), target_name, entity_type)
                send(chat_id, "What do you want to dig into next?", buttons=followup_buttons)
            else:
                send_long(chat_id, final)
                archive_text(final, target_name or "search")
                time.sleep(0.5)
                send(chat_id, "What next?", buttons=[
                    [("🔍 New search","back_main"), ("🔬 Go deeper","deeper")],
                    [("📦 Archive session","cmd_archive"), ("📁 Reports","recent")],
                ])

        except Exception as e:
            log.error(f"Handle error: {e}", exc_info=True)
            send(chat_id, f"Error: {e}")
        finally:
            HDB.mark_done(user_id)

    threading.Thread(target=run, daemon=True).start()

# ── Callback router ───────────────────────────────────────────────────────────
def handle_callback(chat_id, user_id, cb):
    log.info(f"CB: {cb}")

    # Flow starters — show intro + prime the conversation
    if cb in MENU.FLOW_INTROS:
        intro = MENU.FLOW_INTROS[cb]
        send(chat_id, intro["text"], buttons=intro["buttons"])
        # Prime memory with the flow context
        flow_to_protocol = {
            "flow_company":   "company",
            "flow_person":    "person",
            "flow_deep":      "deep",
            "flow_sanctions": "sanctions",
            "flow_phone":     "phone",
            "flow_email":     "email",
            "flow_domain":    "domain",
            "flow_username":  "username",
            "flow_watch":     "watch",
            "flow_finance":   "finance",
        }
        if cb == "flow_agent":
            MEM.set_meta(user_id, "agent_mode_active", True)
            MEM.set_meta(user_id, "pending_protocol", None)
            intro = MENU.FLOW_INTROS.get("flow_agent", {})
            send(chat_id, intro.get("text", "Agent mode active. What do you want to investigate?"))
            HDB.mark_done(user_id)
            return

        if cb in flow_to_protocol:
            proto = flow_to_protocol[cb]
            WIZARD.start_wizard(user_id, proto)
            msg = WIZARD.build_question_message(user_id)
            send(chat_id, msg["text"], buttons=msg["buttons"])
        return

    if cb == "back_main":
        m = MENU.main_menu()
        send(chat_id, m["text"], buttons=m["buttons"])
        return

    if cb == "show_kb":
        send(chat_id, MENU.KB_TEXT, buttons=[[("🔍 New search","back_main")]])
        return

    if cb == "cases_high":
        cases = CASEFILE.get_high_risk_cases(limit=10)
        if not cases:
            send(chat_id, "No HIGH risk cases on file.")
        else:
            lines = ["🔴 HIGH RISK CASES\n━━━━━━━━━━━━━━"]
            for c in cases:
                lines.append(CASEFILE.format_case_summary(c))
                lines.append("")
            send(chat_id, "\n".join(lines), buttons=[[("🔍 New Search","back_main")]])
        return

    if cb == "cases_recent":
        cases = CASEFILE.get_recent_cases(limit=10)
        if not cases:
            send(chat_id, "No cases on file yet.")
        else:
            lines = ["📁 RECENT CASES\n━━━━━━━━━━━━━━"]
            for c in cases:
                lines.append(CASEFILE.format_case_summary(c))
                lines.append("")
            send(chat_id, "\n".join(lines), buttons=[[("🔍 New Search","back_main")]])
        return

    if cb == "recent":
        show_recent(chat_id)
        return

    if cb == "cmd_archive":
        cmd_archive_dump(chat_id, user_id)
        return

    if cb == "clear":
        MEM.clear_history(user_id)
        send(chat_id, "Memory cleared.", buttons=[[("🔍 Start fresh","back_main")]])
        return

    if cb == "upgrades":
        send(chat_id, LEARNER.get_upgrades_summary(),
             buttons=[[("🔍 New search","back_main")]])
        return

    # ── WIZARD CALLBACKS ──────────────────────────────────────────────────────
    # ── FOLLOW-UP CALLBACKS ──────────────────────────────────────────────────
    if cb.startswith("followup_entity:") or cb.startswith("followup_person:"):
        target = cb.split(":",1)[1]
        proto  = "person" if "person" in cb else "company"
        WIZARD.start_wizard(user_id, proto)
        # Pre-fill name
        import sys as _s; _s.path.insert(0,"/home/jarvis/.openclaw/workspace/osint/agent")
        import intake as INTAKE
        params = INTAKE.parse_intake(target, proto_hint=proto)
        WIZARD.answer_question(user_id, target)  # fill name step
        # Skip rest and fire directly
        answers = WIZARD.get_answers(user_id)
        answers["name"] = target
        final_params = WIZARD.build_params_from_answers(answers, proto)
        WIZARD.clear_wizard(user_id)
        MEM.set_meta(user_id, "active_protocol", proto)
        MEM.set_meta(user_id, "protocol_params", final_params)
        MEM.set_meta(user_id, "pending_protocol", None)
        MEM.add_turn(user_id, "user", f"Investigate: {target} [{proto}]")
        handle(chat_id, user_id, f"Investigate {target}")
        return

    if cb.startswith("followup_domain:"):
        domain = cb.split(":",1)[1]
        params = {"name":domain,"domain":domain,"entity_type":"domain","depth":"standard"}
        MEM.set_meta(user_id, "active_protocol",  "domain")
        MEM.set_meta(user_id, "protocol_params",  params)
        MEM.add_turn(user_id, "user", f"Investigate domain: {domain}")
        handle(chat_id, user_id, f"Domain: {domain}")
        return

    if cb.startswith("followup_phone:"):
        phone = cb.split(":",1)[1]
        params = {"name":phone,"phone":phone,"entity_type":"phone","depth":"standard"}
        MEM.set_meta(user_id, "active_protocol",  "phone")
        MEM.set_meta(user_id, "protocol_params",  params)
        MEM.add_turn(user_id, "user", f"Investigate phone: {phone}")
        handle(chat_id, user_id, f"Phone: {phone}")
        return

    if cb.startswith("followup_email:"):
        email = cb.split(":",1)[1]
        params = {"name":email,"email":email,"entity_type":"email","depth":"standard"}
        MEM.set_meta(user_id, "active_protocol",  "email")
        MEM.set_meta(user_id, "protocol_params",  params)
        MEM.add_turn(user_id, "user", f"Investigate email: {email}")
        handle(chat_id, user_id, f"Email: {email}")
        return

    if cb.startswith("followup_spiderfoot:"):
        target = cb.split(":",1)[1]
        send(chat_id, f"Running SpiderFoot on {target}... (up to 90s)")
        import spiderfoot as SF
        result = SF.run_scan(target, "domain_passive", timeout_sec=90)
        brief  = SF.format_for_brief(result)
        send(chat_id, brief)
        return

    if cb.startswith("followup_network:"):
        target = cb.split(":",1)[1]
        MEM.add_turn(user_id, "user", f"Map full network for {target}")
        handle(chat_id, user_id, f"Map the complete network and all associated entities for {target}")
        return

    if cb == "ob_step1":
        ob = ONBOARD.get_step1(user_id)
        send(chat_id, ob["text"], buttons=ob["buttons"]); return

    if cb in ("ob_done", "ob_start"):
        ONBOARD.complete(user_id)
        if cb == "ob_start":
            m = MENU.main_menu()
            send(chat_id, m["text"], buttons=m["buttons"]); return
        send(chat_id, "Welcome to Herkulio. Type /menu to start."); return

    if cb == "upgrade_info":
        send(chat_id,
            "HERKULIO INTELLIGENCE — PLANS\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Free    — 5 searches/month, no PDF\n"
            "Pro     — $29/mo — unlimited + PDF dossiers\n"
            "Business — $99/mo — white-label PDF + API\n\n"
            "Reply UPGRADE PRO or UPGRADE BUSINESS to get access.")
        return

    if cb == "wizard_skip":
        done = WIZARD.answer_question(user_id, "SKIP")
        if done:
            msg = WIZARD.build_summary_message(user_id)
            send(chat_id, msg["text"], buttons=msg["buttons"])
        else:
            msg = WIZARD.build_question_message(user_id)
            send(chat_id, msg["text"], buttons=msg["buttons"])
        return

    if cb == "wizard_fire":
        answers    = WIZARD.get_answers(user_id)
        proto_type = WIZARD.get_proto_type(user_id)
        params     = WIZARD.build_params_from_answers(answers, proto_type)
        WIZARD.clear_wizard(user_id)
        MEM.set_meta(user_id, "active_protocol",  proto_type)
        MEM.set_meta(user_id, "protocol_params",  params)
        MEM.set_meta(user_id, "pending_protocol", None)
        target = params.get("name") or params.get("target","")
        MEM.add_turn(user_id, "user", f"Investigate: {target} [{proto_type}]")
        handle(chat_id, user_id, f"Investigate {target}")
        return

    if cb == "wizard_edit":
        # Restart wizard with same proto type
        proto = WIZARD.get_proto_type(user_id)
        WIZARD.start_wizard(user_id, proto)
        msg = WIZARD.build_question_message(user_id)
        send(chat_id, msg["text"], buttons=msg["buttons"])
        return

    if cb.startswith("wizard_ans:"):
        # Pre-filled answer button (e.g. location shortcuts)
        parts  = cb.split(":", 2)
        field  = parts[1] if len(parts) > 1 else ""
        answer = parts[2] if len(parts) > 2 else ""
        done   = WIZARD.answer_question(user_id, answer)
        if done:
            msg = WIZARD.build_summary_message(user_id)
            send(chat_id, msg["text"], buttons=msg["buttons"])
        else:
            msg = WIZARD.build_question_message(user_id)
            send(chat_id, msg["text"], buttons=msg["buttons"])
        return

    if cb.startswith("skip_clarify:"):
        # User skipped clarification — parse what we have and fire
        parts = cb.split(":", 2)
        proto  = parts[1] if len(parts) > 1 else "person"
        original_text = parts[2] if len(parts) > 2 else ""
        params = INTAKE.parse_intake(original_text, proto_hint=proto)
        MEM.set_meta(user_id, "active_protocol", proto)
        MEM.set_meta(user_id, "protocol_params", params)
        MEM.set_meta(user_id, "pending_protocol", None)
        MEM.add_turn(user_id, "user", original_text)
        handle(chat_id, user_id, original_text)
        return

    if cb == "deeper":
        hist = MEM.get_history(user_id)
        last_target = ""
        for m in reversed(hist):
            t = re.search(r'"target":\s*"([^"]+)"', m.get("content",""))
            if t: last_target = t.group(1); break
        if last_target:
            handle(chat_id, user_id,
                   f"Deep scan on {last_target} — maximum depth, all tools")
        else:
            send(chat_id, "What do you want a deeper scan on?")
        return

    # Quick verdict — one-screen summary from last report
    if cb.startswith("quick_verdict:"):
        target_qv = cb.split(":",1)[1]
        try:
            import sys as _qv_sys; _qv_sys.path.insert(0, '/home/jarvis/.openclaw/workspace/osint/agent')
            import filter as FILTER
            last_profile = MEM.get_meta(user_id, "last_entity_profile") or {}
            if last_profile:
                verdict = FILTER.build_quick_verdict(last_profile, target_qv)
                send(chat_id, verdict)
            else:
                send(chat_id, f"⚡ No cached profile for {target_qv} — run a search first.")
        except Exception as _qve:
            log.error(f"Quick verdict error: {_qve}")
            send(chat_id, "Quick verdict unavailable — try running /deep for a full report.")
        return

    # Follow-up drill-downs (follow_X:target)
    if ":" in cb:
        action, target = cb.split(":", 1)
        prompt = MENU.get_follow_prompt(action, target)
        handle(chat_id, user_id, prompt)
        return

    # Default
    handle(chat_id, user_id, cb)

# ── Recent reports ────────────────────────────────────────────────────────────
def _tool_label(tool_name: str, params: dict) -> str:
    """Human-readable label for a tool call."""
    labels = {
        "TOOL_OSINT":          f"OSINT: {params.get('target','?')} ({params.get('depth','deep').upper()})",
        "TOOL_SEARCH":         f"Search: {params.get('query','')[:50]}",
        "TOOL_DDG":            f"DDG: {params.get('query','')[:50]}",
        "TOOL_INSTAGRAM":      f"Instagram: @{params.get('handle','?')}",
        "TOOL_WHOIS":          f"WHOIS: {params.get('domain','?')}",
        "TOOL_DNS":            f"DNS: {params.get('domain','?')}",
        "TOOL_PHONE":          f"Phone: {params.get('phone','?')}",
        "TOOL_EMAIL":          f"Email: {params.get('email','?')}",
        "TOOL_WAYBACK":        f"Wayback: {params.get('url','?')[:40]}",
        "TOOL_COMPANY":        f"Corporate: {params.get('name','?')}",
        "TOOL_SANCTIONS":      f"Sanctions: {params.get('name','?')}",
        "TOOL_SHERLOCK":       f"Username: {params.get('username','?')}",
        "TOOL_REQ_QUEBEC":     f"REQ Quebec: {params.get('name','?')}",
        "TOOL_SUNBIZ_PW":      f"Sunbiz FL: {params.get('name','?')}",
        "TOOL_LINKEDIN":       f"LinkedIn: {params.get('name','?')}",
        "TOOL_GMAPS":          f"GMaps: {params.get('query','?')}",
        "TOOL_COURTS":         f"Courts: {params.get('name','?')}",
        "TOOL_COURTLISTENER":  f"CourtListener: {params.get('name','?')}",
        "TOOL_PEOPLE_SEARCH":  f"People: {params.get('name','?')} {params.get('city','')}",
        "TOOL_PASTE_SEARCH":   f"Paste: {params.get('query','?')[:40]}",
        "TOOL_SCRAPE_PW":      f"CF Bypass: {params.get('url','?')[:40]}",
        "TOOL_SOCID":          f"SocialIDs: {params.get('url','?')[:40]}",
        "TOOL_EXPAND_NETWORK": f"Network expand: {len(params.get('people',[]))} principals",
    }
    return labels.get(tool_name, tool_name)


def show_recent(chat_id):
    files = sorted(
        [f for f in os.listdir(REPORTS_DIR) if f.endswith(".json")], reverse=True
    )[:10]
    if not files:
        send(chat_id, "No reports yet.", buttons=[[("🔍 Start search","back_main")]])
        return
    lines = ["📁 INTELLIGENCE ARCHIVE\n━━━━━━━━━━━━━━"]
    for f in files:
        p = f.replace(".json","").split("_",2)
        if len(p) >= 3:
            d, t, name = p
            dt   = f"{d[:4]}-{d[4:6]}-{d[6:]} {t[:2]}:{t[2:4]}"
            risk = "⚪"
            try:
                rd   = json.load(open(os.path.join(REPORTS_DIR,f)))
                risk = {"HIGH":"🔴","MEDIUM":"🟡","LOW":"🟢"}.get(rd.get("risk_rating",""),"⚪")
            except: pass
            lines.append(f"{risk} {dt} — {name.replace('_',' ').title()}")
    send(chat_id, "\n".join(lines),
         buttons=[[("🔍 New search","back_main"),("📦 Archive session","cmd_archive")]])

# ── Main polling loop ─────────────────────────────────────────────────────────
def main():
    log.info(f"HERKULIO INTELLIGENCE 🔴 | Brain: {BRAIN.OR_MODEL} | Key: {'OK' if BRAIN.OR_KEY else 'MISSING'}")
    log.info(f"Skills: {len(SKILLS.list_skills())} | Tools: {len(TOOLS.TOOL_MAP)} | Flows: {len(MENU.FLOW_INTROS)}")
    offset = 0
    while True:
        try:
            updates = tg("getUpdates", offset=offset, timeout=30,
                         allowed_updates=["message","callback_query"]).get("result",[])
            for upd in updates:
                offset = upd["update_id"] + 1

                if "callback_query" in upd:
                    cq      = upd["callback_query"]
                    chat_id = cq["message"]["chat"]["id"]
                    user_id = cq["from"]["id"]
                    answer_cb(cq["id"])
                    if ID.is_authorized(user_id):
                        handle_callback(chat_id, user_id, cq.get("data",""))
                    continue

                msg     = upd.get("message",{})
                if not msg: continue
                chat_id = msg["chat"]["id"]
                user_id = msg["from"]["id"]
                text    = msg.get("text","").strip()

                # ── DOCUMENT INTELLIGENCE HANDLER (PDF/DOC) ──────────────────
                doc_msg = msg.get("document",{})
                doc_mime = doc_msg.get("mime_type","")
                is_pdf = "pdf" in doc_mime or doc_msg.get("file_name","").lower().endswith(".pdf")
                if not msg.get("text","") and is_pdf and doc_msg.get("file_id"):
                    if not ID.is_authorized(user_id):
                        send(chat_id, "Access restricted."); continue
                    try:
                        import sys as _di_sys; _di_sys.path.insert(0, '/home/jarvis/.openclaw/workspace/osint/agent')
                        import doc_intel as DOC
                        typing(chat_id)
                        send(chat_id, "📄 Analyzing document metadata...")
                        result = DOC.analyze_document(doc_msg["file_id"], doc_msg.get("file_name","document.pdf"))
                        send(chat_id, result["report_text"],
                             buttons=[[("🔍 New investigation","back_main"),
                                       ("📄 Analyze another","back_main")]])
                        log.info("Doc intel: risk=%s author=%s", result.get("risk_level"), result.get("author"))
                    except Exception as _de:
                        log.error("Doc handler error: %s", _de)
                        send(chat_id, "❌ Document analysis failed.")
                    continue

                # ── PHOTO INTELLIGENCE HANDLER ────────────────────────────────
                photo   = msg.get("photo") or (msg.get("document",{}) if msg.get("document",{}).get("mime_type","").startswith("image") else None)
                # Also handle photo with caption
                if not text and msg.get("caption"):
                    text = msg.get("caption","").strip()
                if photo and (not text or any(w in text.lower() for w in ["analyze","exif","photo","metadata","check","scan"])):
                    if not ID.is_authorized(user_id):
                        send(chat_id, "Access restricted."); continue
                    try:
                        import sys as _pi_sys; _pi_sys.path.insert(0, '/home/jarvis/.openclaw/workspace/osint/agent')
                        import photo_intel as PHOTO
                        typing(chat_id)
                        send(chat_id, "🔍 Analyzing photo metadata...")
                        # Get highest-res photo or document
                        if isinstance(photo, list):
                            file_id   = sorted(photo, key=lambda p: p.get("file_size",0))[-1]["file_id"]
                            file_name = "photo.jpg"
                        else:
                            file_id   = photo["file_id"]
                            file_name = photo.get("file_name","document.jpg")
                        result = PHOTO.analyze_photo(file_id, file_name)
                        send(chat_id, result["report_text"],
                             buttons=[[("🔍 New investigation","back_main"),
                                       ("📸 Analyze another","back_main")]])
                        log.info(f"Photo intel: gps={result.get('has_gps')} edits={result.get('has_edits')}")
                    except Exception as _pe:
                        log.error(f"Photo handler error: {_pe}")
                        send(chat_id, "❌ Photo analysis failed. Make sure ExifTool is installed.")
                    continue

                if not text: continue
                if not ID.is_authorized(user_id):
                    USERDB.get_or_create_user(user_id, "")
                    send(chat_id, "Access restricted."); continue

                log.info(f"[{user_id}] {text[:80]}")
                cmd = text.split()[0].lower().split("@")[0]

                # ── WIZARD IN PROGRESS: treat text as answer ──────────────────
                if WIZARD.is_active(user_id) and not cmd.startswith("/"):
                    done = WIZARD.answer_question(user_id, text)
                    if done:
                        msg = WIZARD.build_summary_message(user_id)
                        send(chat_id, msg["text"], buttons=msg["buttons"])
                    else:
                        msg = WIZARD.build_question_message(user_id)
                        send(chat_id, msg["text"], buttons=msg["buttons"])
                    continue

                if cmd == "/start":
                    # Don't clear history on /start — user may hit it accidentally
                    # New user onboarding
                    USERDB.get_or_create_user(user_id, "")
                    if ONBOARD.is_complete(user_id) is False:
                        ob = ONBOARD.get_welcome(user_id)
                        send(chat_id, ob["text"], buttons=ob["buttons"]); continue
                    m = MENU.main_menu()
                    researched = len(MEM.get_researched(user_id))
                    send(chat_id,
                         f"HERKULIO v1.0 — ONLINE 🔴\n"
                         f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                         f"Brain:   Qwen3-235b (HERKULIO v1.0)\n"
                         f"Memory:  {researched} targets researched\n"
                         f"Skills:  watch-osint active\n"
                         f"Tools:   {len(TOOLS.TOOL_MAP)} tools | 55+ modules\n"
                         f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                         f"What are we investigating?",
                         buttons=m["buttons"])

                elif cmd == "/menu":
                    m = MENU.main_menu()
                    send(chat_id, m["text"], buttons=m["buttons"])

                elif cmd == "/help":
                    help_text = (
                        "HERKULIO INTELLIGENCE — COMMANDS\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        "SEARCH\n"
                        "/menu — Open search menu\n"
                        "/clear — Reset session\n\n"
                        "REPORTS\n"
                        "/archive — Generate CIA dossier PDF\n"
                        "/cases — View all saved cases\n"
                        "/recent — Last 5 searches\n\n"
                        "SYSTEM\n"
                        "/status — Engine + tool status\n"
                        "/upgrades — Pending improvements\n"
                        "/recall — What I remember about you\n\n"
                        "PHOTO INTELLIGENCE\n"
                        "Send any photo → GPS, timestamps, device, edit detection\n"
                        "Send as file for full uncompressed metadata\n\n"
                        "TIP: You can also just type any name,\n"
                        "company, phone, email, or domain directly."
                    )
                    send(chat_id, help_text, buttons=[[("📋 Open Menu","main_menu")]])

                elif cmd == "/archive":
                    cmd_archive_dump(chat_id, user_id)

                elif cmd == "/upgrades":
                    send(chat_id, LEARNER.get_upgrades_summary(),
                         buttons=[[("🔍 New search","back_main")]])

                elif cmd == "/clear":
                    MEM.clear_history(user_id)
                    send(chat_id, "Memory cleared.")

                elif cmd == "/admin":
                    if user_id in ID.AUTHORIZED_ADMINS:
                        send(chat_id, ADMIN.get_dashboard())
                    else:
                        send(chat_id, "Access denied.")

                elif cmd == "/setplan":
                    # /setplan <user_id> <tier>
                    parts = text.strip().split()
                    if user_id in ID.AUTHORIZED_ADMINS and len(parts) == 3:
                        result = ADMIN.set_user_tier_admin(parts[1], parts[2])
                        send(chat_id, result)
                    else:
                        send(chat_id, "Usage: /setplan <user_id> <tier>  (owner only)")

                elif cmd == "/account":
                    send(chat_id, USERDB.format_status_message(user_id))

                elif cmd == "/status":
                    researched = MEM.get_researched(user_id)
                    turns      = MEM.turn_count(user_id)
                    count      = len([f for f in os.listdir(REPORTS_DIR) if f.endswith(".json")])
                    learned    = json.load(open(LEARNER.LEARNER_FILE)) if os.path.exists(LEARNER.LEARNER_FILE) else {}
                    send(chat_id,
                         f"HERKULIO v1.0 — ONLINE 🔴\n━━━━━━━━━━━━━━\n"
                         f"Brain:        {BRAIN.OR_MODEL}\n"
                         f"Tools:        {len(TOOLS.TOOL_MAP)} | 55+ modules\n"
                         f"Reports:      {count} archived\n"
                         f"This session: {len(researched)} targets\n"
                         f"Memory turns: {turns}\n"
                         f"Roadblocks:   {len(learned.get('roadblocks',[]))}\n"
                         f"Corrections:  {len(learned.get('corrections',[]))}\n"
                         f"━━━━━━━━━━━━━━",
                         buttons=[[("📁 Reports","recent"),
                                   ("🧠 Upgrades","upgrades"),
                                   ("🗑 Clear","clear")]])

                elif cmd == "/cases":
                    # Show case database
                    stats = CASEFILE.get_stats()
                    send(chat_id, CASEFILE.format_stats(stats),
                         buttons=[
                             [("🔴 High Risk Cases","cases_high"),
                              ("📁 All Recent","cases_recent")],
                             [("🔍 New Search","back_main")],
                         ])

                elif cmd == "/recall":
                    # Recall a specific case by name
                    query = " ".join(text.split()[1:]).strip()
                    if not query:
                        send(chat_id, "Usage: /recall Company Name")
                    else:
                        cases = CASEFILE.find_cases(query, limit=5)
                        if not cases:
                            send(chat_id, f"No cases found for: {query}")
                        else:
                            lines = [f"🗂 CASES MATCHING: {query}\n━━━━━━━━━━━━━━"]
                            for c in cases:
                                lines.append(CASEFILE.format_case_summary(c))
                                lines.append("")
                            send(chat_id, "\n".join(lines),
                                 buttons=[[("🔍 New Search","back_main")]])

                elif cmd == "/recent":
                    show_recent(chat_id)

                else:
                    handle(chat_id, user_id, text)

        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"Loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
