"""
Nexus Layer 2 - Gemini-Powered Natural Language Query Engine
Uses Google Gemini API + Weaviate Vector Search for intelligent CTG querying
Single-file: combines NL parsing, semantic search, Cypher generation, and analysis
"""

import os
import sys
import json
import re
import time
from pathlib import Path

# Fix Windows encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable
from cypher_queries import NEXUS_QUERIES

# ── Gemini SDK (new google.genai) ──────────────────────────
try:
    from google import genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# ── Weaviate SDK ───────────────────────────────────────────
try:
    import weaviate
    from weaviate.auth import AuthApiKey
    from weaviate.classes.query import MetadataQuery
    HAS_WEAVIATE = True
except ImportError:
    HAS_WEAVIATE = False

# ── Colorama ───────────────────────────────────────────────
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class Fore:
        GREEN = CYAN = YELLOW = RED = MAGENTA = BLUE = WHITE = ""
    class Style:
        BRIGHT = RESET_ALL = ""

# ── Config ─────────────────────────────────────────────────
NEO4J_URI = "bolt://localhost:7687"
GEMINI_MODEL = "gemini-2.5-flash"
WEAVIATE_URL = "https://xgysxhhosmiqqawovgtguq.c0.asia-southeast1.gcp.weaviate.cloud"
WEAVIATE_KEY = "YVN1enphUHBqSUNIMkRlal96Um8yUEpLSzEyaWViaEFEK0tTdlUwZzA4SGNBU1pUYlc1ZDVZbEU3K3RJPV92MjAw"
WEAVIATE_COLLECTION = "NexusDPR"

SYSTEM_PROMPT = (
    "You are Nexus CTG Query Assistant analyzing a PostgreSQL architectural "
    "decision graph (Causal Temporal Graph) in Neo4j.\n"
    "DPR nodes have: dpr_id, title, component, blast_radius_estimate "
    "(critical/high/medium/low), assumption_decay_risk (high/medium/low), "
    "active_workarounds, decision, within_window, intended_durability.\n"
    "DecayAlert nodes linked via HAS_ALERT.\n"
    "Relationships: CONSTRAINS, ENABLES, REQUIRES, ASSUMPTION_OF, "
    "TEMPORAL_PRECEDES, REQUIRED_BY, HAS_ALERT.\n"
    "Components: MVCC, WAL, Storage, Autovacuum, ProcessModel, Replication.\n"
    "Provide clear, concise analysis with risks and recommendations."
)

CYPHER_GEN_PROMPT = (
    "Generate a Cypher query for this Neo4j graph question. "
    "Labels: DPR, DecayAlert. "
    "DPR props: dpr_id, title, component, within_window, decision_date, "
    "decision, blast_radius_estimate, assumption_decay_risk, "
    "intended_durability, active_workarounds, files_involved, "
    "commit_refs, involved_humans, decay_risk_reasoning, "
    "blast_radius_reasoning, durability_reasoning. "
    "DecayAlert props: dpr_id, assumption, already_decaying, "
    "decay_evidence, earliest_signal_date. "
    "Rels: CONSTRAINS, ENABLES, REQUIRES, ASSUMPTION_OF, "
    "TEMPORAL_PRECEDES, REQUIRED_BY, HAS_ALERT. "
    "Return ONLY the Cypher query. If impossible, return NONE.\n\n"
    "Question: {question}"
)


# ── Neo4j ──────────────────────────────────────────────────
def connect_neo4j(uri=NEO4J_URI):
    try:
        driver = GraphDatabase.driver(uri, auth=None)
        driver.verify_connectivity()
        return driver
    except Exception as e:
        print(f"{Fore.RED}[X] Neo4j: {e}{Style.RESET_ALL}")
        return None


def run_cypher(driver, cypher, params=None):
    try:
        with driver.session() as s:
            return [dict(r) for r in s.run(cypher, **(params or {}))]
    except Exception as e:
        return [{"error": str(e)}]


# ── Weaviate ───────────────────────────────────────────────
def connect_weaviate():
    if not HAS_WEAVIATE:
        return None
    try:
        url = os.getenv("WEAVIATE_URL", WEAVIATE_URL)
        key = os.getenv("WEAVIATE_KEY", WEAVIATE_KEY)
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=url,
            auth_credentials=AuthApiKey(key),
        )
        if client.is_ready():
            return client
        return None
    except Exception as e:
        print(f"{Fore.YELLOW}[!] Weaviate: {e}{Style.RESET_ALL}")
        return None


def weaviate_search(client, query, limit=5):
    """Semantic search over DPRs in Weaviate."""
    if client is None:
        return []
    try:
        collection = client.collections.get(WEAVIATE_COLLECTION)
        results = collection.query.near_text(
            query=query,
            limit=limit,
            return_metadata=MetadataQuery(distance=True, certainty=True),
        )
        output = []
        for obj in results.objects:
            p = obj.properties
            m = obj.metadata
            output.append({
                "dpr_id": p.get("dpr_id"),
                "title": p.get("title"),
                "component": p.get("component"),
                "decision": p.get("decision", "")[:200],
                "decay_risk": p.get("decay_risk"),
                "blast_radius": p.get("blast_radius"),
                "certainty": round(m.certainty, 4) if m.certainty else None,
            })
        return output
    except Exception as e:
        print(f"{Fore.YELLOW}[!] Weaviate search: {e}{Style.RESET_ALL}")
        return []


# ── Gemini ─────────────────────────────────────────────────
def setup_gemini(api_key=None):
    if not HAS_GEMINI:
        return None
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        print(f"{Fore.YELLOW}[!] Set GEMINI_API_KEY env var{Style.RESET_ALL}")
        return None
    return genai.Client(api_key=key)


def ask_gemini(client, prompt, system=None):
    if client is None:
        return None
    try:
        config = None
        if system:
            config = genai.types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.3,
            )
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        return resp.text.strip()
    except Exception as e:
        print(f"{Fore.RED}[X] Gemini: {e}{Style.RESET_ALL}")
        return None


# ── Local Keyword Mapper (fast fallback) ───────────────────
def local_match(question):
    q = question.lower()

    # DPR-specific causal queries
    m = re.search(r'DPR-\d+', question, re.IGNORECASE)
    if m:
        dpr_id = m.group(0).upper()
        if any(k in q for k in ["what led to", "why", "caused by", "history"]):
            return "causal_chain_to", {"dpr_id": dpr_id}
        if any(k in q for k in ["impact", "downstream", "affect", "enable"]):
            return "causal_chain_from", {"dpr_id": dpr_id}

    # Component subgraph
    comps = {"mvcc": "MVCC", "wal": "WAL", "storage": "Storage",
             "autovacuum": "Autovacuum", "process": "ProcessModel",
             "replication": "Replication"}
    if "component" in q or "subgraph" in q:
        for k, v in comps.items():
            if k in q:
                return "component_subgraph", {"component": v}

    # Keyword -> query map
    rules = [
        (["most dangerous", "highest risk", "critical and high"], "high_risk_critical_blast"),
        (["blast radius", "critical", "dangerous"], "critical_blast_radius"),
        (["already decaying", "decay signal", "breaking"], "already_decaying"),
        (["high risk", "risky assumption", "decay risk"], "high_decay_risk"),
        (["decay timeline", "when did decay"], "decay_timeline"),
        (["foundational", "core decision", "fundamental"], "foundational_decisions"),
        (["workaround proliferat", "many workaround"], "workaround_proliferation"),
        (["workaround", "hack", "technical debt"], "active_workarounds"),
        (["recent", "last 2 years", "within window"], "within_window_changes"),
        (["most connected", "central", "hub", "influential"], "most_connected_dprs"),
        (["constrains", "constraint", "limits"], "constrains_relationships"),
        (["enables", "allows", "makes possible"], "enables_relationships"),
        (["requires", "needs", "depends"], "requires_relationships"),
        (["stats", "statistics", "overview", "summary"], "full_graph_stats"),
        (["component depend", "cross-component"], "component_dependencies"),
        (["assumption", "assumes"], "assumption_chain"),
    ]
    for keywords, qname in rules:
        if any(k in q for k in keywords):
            return qname, {}

    return None, None


# ── Main Query Pipeline ───────────────────────────────────
def nexus_query(question, driver=None, gemini_client=None, weaviate_client=None):
    """Process NL question -> Cypher -> Results -> Analysis"""
    own_driver = driver is None
    if own_driver:
        driver = connect_neo4j()
        if not driver:
            return "Cannot connect to Neo4j."

    try:
        records = []

        # 1) Local keyword match (fast)
        qname, params = local_match(question)
        if qname and qname in NEXUS_QUERIES:
            cypher = NEXUS_QUERIES[qname]["cypher"]
            records = run_cypher(driver, cypher, params)

        # 2) Weaviate semantic search (enrich context)
        semantic_context = ""
        if weaviate_client:
            wv_results = weaviate_search(weaviate_client, question, limit=5)
            if wv_results:
                print(f"{Fore.BLUE}[*] Weaviate: {len(wv_results)} semantic matches{Style.RESET_ALL}")
                semantic_context = json.dumps(wv_results, indent=2, default=str)

        # 3) Gemini Cypher generation (if no local match)
        if not records and gemini_client:
            print(f"{Fore.CYAN}[*] Gemini generating Cypher...{Style.RESET_ALL}")
            cypher = ask_gemini(gemini_client, CYPHER_GEN_PROMPT.format(question=question))
            if cypher and cypher != "NONE" and "MATCH" in cypher.upper():
                cypher = cypher.replace("```cypher", "").replace("```", "").strip()
                print(f"{Fore.WHITE}[>] {cypher[:80]}...{Style.RESET_ALL}")
                records = run_cypher(driver, cypher)
                if records and "error" in records[0]:
                    records = []

        # 3) Format results
        if records and not any("error" in r for r in records):
            raw = json.dumps(records[:15], indent=2, default=str)

            # If Gemini available, get analysis
            if gemini_client:
                prompt = (
                    f'User asked: "{question}"\n\n'
                    f"Neo4j Results:\n{raw}\n\n"
                )
                if semantic_context:
                    prompt += f"Weaviate Semantic Matches:\n{semantic_context}\n\n"
                prompt += (
                    "Provide a clear answer with bullet points. "
                    "Highlight risks and recommendations."
                )
                analysis = ask_gemini(gemini_client, prompt, SYSTEM_PROMPT)
                if analysis:
                    return analysis

            # Plain text fallback
            out = []
            if qname:
                out.append(f"Query: {NEXUS_QUERIES[qname]['description']}")
            out.append(f"Found {len(records)} results:\n")
            for r in records[:10]:
                out.append(str({k: v for k, v in r.items() if v}))
            return "\n".join(out)

        # 4) Direct Gemini answer (with semantic context if available)
        if gemini_client:
            prompt = f"About the PostgreSQL CTG graph, answer: {question}"
            if semantic_context:
                prompt += f"\n\nRelevant DPRs from semantic search:\n{semantic_context}"
            return ask_gemini(
                gemini_client,
                prompt,
                SYSTEM_PROMPT,
            ) or "Could not process question."

        return (
            "No match found. Try:\n"
            "  - What decisions have critical blast radius?\n"
            "  - What assumptions are decaying?\n"
            "  - What led to DPR-003?\n"
            "  - Show graph statistics"
        )

    finally:
        if own_driver:
            driver.close()


# ── REPL ───────────────────────────────────────────────────
def main():
    print(f"""{Fore.CYAN}{Style.BRIGHT}
==============================================================
   N E X U S   C T G   Q U E R Y   E N G I N E
   Powered by Google Gemini + Neo4j + Weaviate
=============================================================={Style.RESET_ALL}""")

    driver = connect_neo4j()
    if not driver:
        print(f"{Fore.RED}Start Neo4j: docker run -p7474:7474 -p7687:7687 neo4j:community{Style.RESET_ALL}")
        return

    recs = run_cypher(driver, "MATCH (d:DPR) RETURN count(d) as c")
    count = recs[0]["c"] if recs else 0
    print(f"{Fore.GREEN}[+] Neo4j: {count} DPR nodes{Style.RESET_ALL}")

    client = setup_gemini()
    wv = connect_weaviate()
    
    engines = []
    if client: engines.append("Gemini")
    if wv: engines.append("Weaviate")
    engines.append("local")
    mode = " + ".join(engines)
    print(f"{Fore.GREEN}[+] Weaviate: {'connected' if wv else 'not available'}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}[+] Mode: {mode}{Style.RESET_ALL}\n")

    print(f"{Fore.YELLOW}Examples:{Style.RESET_ALL}")
    for ex in [
        "What decisions have critical blast radius?",
        "What assumptions are already decaying?",
        "What led to DPR-003?",
        "Show the most dangerous decisions",
        "What workarounds exist?",
        "Show graph stats",
    ]:
        print(f"  - {ex}")
    print(f"\n{Fore.WHITE}Type 'exit' to quit.{Style.RESET_ALL}\n")

    while True:
        try:
            q = input(f"{Fore.MAGENTA}{Style.BRIGHT}nexus> {Style.RESET_ALL}").strip()
            if not q:
                continue
            if q.lower() in ("exit", "quit", "q"):
                break
            if q.lower() == "stats":
                from verify_graph import verify_graph
                verify_graph()
                continue
            if q.lower().startswith("search "):
                # Direct Weaviate semantic search
                sq = q[7:].strip()
                results = weaviate_search(wv, sq, limit=5)
                if results:
                    print(f"\n{Fore.BLUE}Semantic Results:{Style.RESET_ALL}")
                    for i, r in enumerate(results, 1):
                        cert = f"{r['certainty']:.1%}" if r['certainty'] else "N/A"
                        print(f"  [{i}] {r['dpr_id']}: {r['title']} ({cert})")
                        print(f"      {r['component']} | Risk: {r['decay_risk']} | Blast: {r['blast_radius']}")
                else:
                    print(f"{Fore.YELLOW}No semantic results.{Style.RESET_ALL}")
                continue

            t = time.time()
            result = nexus_query(q, driver, client, wv)
            print(f"\n{Fore.GREEN}[>] {time.time()-t:.2f}s{Style.RESET_ALL}")
            print("=" * 60)
            print(result)
            print("=" * 60 + "\n")
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}\n")

    driver.close()
    if wv:
        wv.close()
    print(f"{Fore.CYAN}Goodbye!{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
