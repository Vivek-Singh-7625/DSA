"""
Nexus — Unified LLM Provider
Supports IBM WatsonX AI (primary), Groq (free, no credit card), Google Gemini.
Chunked/small-packet generation for large prompts.

Environment Variables:
  WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL, WATSONX_MODEL
  GROQ_API_KEY         — Groq API key (free at console.groq.com, no credit card)
  GROQ_MODEL           — Groq model (default: llama-3.3-70b-versatile)
  GEMINI_API_KEY, LLM_PROVIDER, LLM_CHUNK_SIZE
"""

import os, sys, json, re, time, math
import httpx
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

HAS_WATSONX = False
HAS_GEMINI = False

try:
    from ibm_watsonx_ai.foundation_models import ModelInference
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
    from ibm_watsonx_ai import Credentials, APIClient
    HAS_WATSONX = True
except ImportError:
    pass

try:
    from google import genai
    HAS_GEMINI = True
except ImportError:
    pass

DEFAULT_CHUNK_SIZE = int(os.environ.get("LLM_CHUNK_SIZE", "4000"))

@dataclass
class LLMUsageStats:
    provider: str = ""
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    calls_log: list = field(default_factory=list)
    errors: int = 0
    start_time: str = ""
    chunked_calls: int = 0

    def log_call(self, prompt_len, response_len, model, latency, is_chunk=False):
        self.total_calls += 1
        self.total_input_tokens += prompt_len // 4
        self.total_output_tokens += response_len // 4
        if is_chunk:
            self.chunked_calls += 1
        self.calls_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model, "input_chars": prompt_len,
            "output_chars": response_len, "latency_s": round(latency, 2),
            "is_chunk": is_chunk,
        })

    def to_dict(self):
        return {
            "provider": self.provider, "total_calls": self.total_calls,
            "total_input_tokens_est": self.total_input_tokens,
            "total_output_tokens_est": self.total_output_tokens,
            "chunked_calls": self.chunked_calls, "errors": self.errors,
            "start_time": self.start_time, "recent_calls": self.calls_log[-20:],
        }

_usage = LLMUsageStats()

def get_usage_stats():
    return _usage.to_dict()


class WatsonXProvider:
    DEFAULT_URL = "https://us-south.ml.cloud.ibm.com"
    DEFAULT_MODEL = "ibm/granite-3-8b-instruct"

    def __init__(self):
        self.api_key = os.environ.get("WATSONX_API_KEY", "")
        self.project_id = os.environ.get("WATSONX_PROJECT_ID", "")
        self.url = os.environ.get("WATSONX_URL", self.DEFAULT_URL)
        self.model_id = os.environ.get("WATSONX_MODEL", self.DEFAULT_MODEL)
        self.client = None
        self.model = None
        self._connect()

    def _connect(self):
        try:
            creds = Credentials(url=self.url, api_key=self.api_key)
            self.client = APIClient(creds, project_id=self.project_id)
            self.model = ModelInference(
                model_id=self.model_id, api_client=self.client,
                project_id=self.project_id)
            print(f"[+] WatsonX connected: model={self.model_id}")
        except Exception as e:
            print(f"[!] WatsonX connection failed: {e}")
            self.model = None

    @property
    def is_available(self):
        return self.model is not None

    def generate(self, prompt, temperature=0.2, max_tokens=8192,
                 system=None, is_chunk=False):
        if not self.model:
            return None
        full = prompt
        if system:
            full = f"<|system|>\n{system}\n<|user|>\n{prompt}\n<|assistant|>\n"
        params = {
            GenParams.DECODING_METHOD: "greedy" if temperature < 0.1 else "sample",
            GenParams.MAX_NEW_TOKENS: max_tokens,
            GenParams.TEMPERATURE: temperature,
            GenParams.TOP_P: 0.9, GenParams.TOP_K: 50,
            GenParams.REPETITION_PENALTY: 1.1,
        }
        for attempt in range(3):
            try:
                t0 = time.time()
                resp = self.model.generate_text(prompt=full, params=params)
                lat = time.time() - t0
                if resp:
                    _usage.log_call(len(full), len(resp), self.model_id, lat, is_chunk)
                    return resp.strip()
                return None
            except Exception as e:
                print(f"  [!] WatsonX attempt {attempt+1} failed: {e}")
                _usage.errors += 1
                if attempt < 2: time.sleep(3 * (attempt + 1))
        return None


class GeminiProvider:
    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self):
        self.api_key = (os.environ.get("GEMINI_API_KEY")
                        or os.environ.get("GOOGLE_API_KEY") or "")
        self.model_id = os.environ.get("GEMINI_MODEL", self.DEFAULT_MODEL)
        self.client = None
        self._connect()

    def _connect(self):
        try:
            self.client = genai.Client(api_key=self.api_key)
            print(f"[+] Gemini connected: model={self.model_id}")
        except Exception as e:
            print(f"[!] Gemini connection failed: {e}")
            self.client = None

    @property
    def is_available(self):
        return self.client is not None

    def generate(self, prompt, temperature=0.2, max_tokens=65536,
                 system=None, is_chunk=False):
        if not self.client:
            return None
        kw = {"temperature": temperature, "max_output_tokens": max_tokens}
        if system:
            kw["system_instruction"] = system
        config = genai.types.GenerateContentConfig(**kw)
        for attempt in range(3):
            try:
                t0 = time.time()
                resp = self.client.models.generate_content(
                    model=self.model_id, contents=prompt, config=config)
                lat = time.time() - t0
                text = resp.text.strip()
                _usage.log_call(len(prompt), len(text), self.model_id, lat, is_chunk)
                return text
            except Exception as e:
                print(f"  [!] Gemini attempt {attempt+1} failed: {e}")
                _usage.errors += 1
                if attempt < 2: time.sleep(5 * (attempt + 1))
        return None


class GroqProvider:
    """Groq API provider — FREE, no credit card needed.
    Sign up at https://console.groq.com — get API key instantly.
    Uses OpenAI-compatible API with httpx."""

    DEFAULT_MODEL = "llama-3.3-70b-versatile"
    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        self.model_id = os.environ.get("GROQ_MODEL", self.DEFAULT_MODEL)
        self._available = bool(self.api_key)
        if self._available:
            print(f"[+] Groq connected: model={self.model_id} (FREE tier)")
        else:
            print("[!] Groq: GROQ_API_KEY not set")

    @property
    def is_available(self):
        return self._available

    def generate(self, prompt, temperature=0.2, max_tokens=8192,
                 system=None, is_chunk=False):
        if not self._available:
            return None

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": min(max_tokens, 8192),
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(3):
            try:
                t0 = time.time()
                resp = httpx.post(self.API_URL, json=payload,
                                  headers=headers, timeout=120)
                lat = time.time() - t0

                if resp.status_code == 200:
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    _usage.log_call(len(prompt), len(text), self.model_id,
                                    lat, is_chunk)
                    return text
                else:
                    print(f"  [!] Groq HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                print(f"  [!] Groq attempt {attempt+1} failed: {e}")
                _usage.errors += 1
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
        return None


class NexusLLM:
    """Unified LLM: WatsonX → Groq (free) → Gemini. Chunked generation."""

    def __init__(self):
        self.watsonx = None
        self.groq = None
        self.gemini = None
        self.active_provider = "none"
        self.chunk_size = DEFAULT_CHUNK_SIZE
        self._init_providers()

    def _init_providers(self):
        forced = os.environ.get("LLM_PROVIDER", "auto").lower()
        _usage.start_time = datetime.now(timezone.utc).isoformat()

        if forced in ("watsonx", "auto") and HAS_WATSONX:
            if os.environ.get("WATSONX_API_KEY"):
                self.watsonx = WatsonXProvider()
                if self.watsonx.is_available:
                    self.active_provider = "watsonx"
                    _usage.provider = "watsonx"
                    print("[+] Active LLM provider: IBM WatsonX AI")

        # Groq (free, no credit card)
        if forced in ("groq", "auto"):
            if os.environ.get("GROQ_API_KEY"):
                self.groq = GroqProvider()
                if self.groq.is_available and self.active_provider == "none":
                    self.active_provider = "groq"
                    _usage.provider = "groq"
                    print("[+] Active LLM provider: Groq (FREE tier)")

        if forced in ("gemini", "auto") and HAS_GEMINI:
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if key:
                self.gemini = GeminiProvider()
                if self.gemini.is_available and self.active_provider == "none":
                    self.active_provider = "gemini"
                    _usage.provider = "gemini"
                    print("[+] Active LLM provider: Google Gemini (fallback)")

        if self.active_provider == "none":
            print("[!] WARNING: No LLM provider available!")
            print("    Easiest: set GROQ_API_KEY (free at console.groq.com)")

    @property
    def is_available(self):
        return self.active_provider != "none"

    @property
    def provider_name(self):
        return self.active_provider

    def generate(self, prompt, temperature=0.2, max_tokens=8192,
                 system=None, is_chunk=False):
        # Try WatsonX first (IBM hackathon primary)
        if self.watsonx and self.watsonx.is_available:
            result = self.watsonx.generate(prompt, temperature, max_tokens, system, is_chunk)
            if result:
                return result
            print("  [!] WatsonX failed, trying Groq...")
        # Try Groq (free, no credit card)
        if self.groq and self.groq.is_available:
            result = self.groq.generate(prompt, temperature, max_tokens, system, is_chunk)
            if result:
                return result
            print("  [!] Groq failed, trying Gemini...")
        # Fallback to Gemini
        if self.gemini and self.gemini.is_available:
            return self.gemini.generate(prompt, temperature, max_tokens, system, is_chunk)
        print("  [!] No LLM provider available")
        return None

    def generate_json(self, prompt, temperature=0.2, max_tokens=8192, system=None):
        raw = self.generate(prompt, temperature, max_tokens, system)
        return self._parse_json(raw) if raw else None

    # ── Chunked / Small-Packet Generation ─────────────────
    def _split_chunks(self, text, chunk_size=None):
        size = chunk_size or self.chunk_size
        if len(text) <= size:
            return [text]
        chunks, remaining = [], text
        while remaining:
            if len(remaining) <= size:
                chunks.append(remaining)
                break
            split_at = size
            for delim in ["\n\n", "\n", ". ", " "]:
                idx = remaining.rfind(delim, 0, size)
                if idx > size // 2:
                    split_at = idx + len(delim)
                    break
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:]
        return chunks

    def generate_chunked(self, instruction, context_sections,
                         temperature=0.2, max_tokens=8192, system=None,
                         progress_callback=None):
        """Send large prompts in small packets. Digests each section separately."""
        print(f"  [Chunked] {len(context_sections)} sections → small packets")
        digested = []
        total = len(context_sections)

        for i, (name, text) in enumerate(context_sections.items()):
            if progress_callback:
                progress_callback(stage="extracting", progress=int(30 + (i/max(total,1))*30))

            chunks = self._split_chunks(text)
            print(f"  [Chunked] '{name}': {len(chunks)} packet(s)")

            if len(chunks) == 1 and len(text) < self.chunk_size:
                digested.append(f"=== {name} ===\n{text}")
                continue

            parts = []
            for j, chunk in enumerate(chunks):
                dp = (f"Summarize concisely, preserving technical details:\n\n"
                      f"SECTION: {name} (part {j+1}/{len(chunks)})\n\n{chunk}")
                d = self.generate(dp, temperature=0.1, max_tokens=2000,
                                  system=system, is_chunk=True)
                if d: parts.append(d)
                time.sleep(0.5)

            combined = "\n".join(parts) if parts else text[:self.chunk_size]
            digested.append(f"=== {name} (digested) ===\n{combined}")

        if progress_callback:
            progress_callback(stage="synthesizing", progress=65)

        final_ctx = "\n\n".join(digested)
        if len(final_ctx) > self.chunk_size * 6:
            final_ctx = final_ctx[:self.chunk_size * 6]

        final = f"{final_ctx}\n\n---\n\n{instruction}"
        print(f"  [Chunked] Final synthesis: {len(final)} chars")
        result = self.generate(final, temperature, max_tokens, system)

        if progress_callback:
            progress_callback(stage="building_graph", progress=70)
        return result

    def generate_json_chunked(self, instruction, context_sections,
                              temperature=0.2, max_tokens=8192, system=None,
                              progress_callback=None):
        raw = self.generate_chunked(instruction, context_sections, temperature,
                                    max_tokens, system, progress_callback)
        return self._parse_json(raw) if raw else None

    def _parse_json(self, raw):
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r'^```\w*\n?', '', cleaned)
            cleaned = re.sub(r'\n?```$', '', cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            m = re.search(r'\{[\s\S]*\}', cleaned)
            if m:
                try: return json.loads(m.group())
                except: pass
        return None

    def status(self):
        return {
            "active_provider": self.active_provider,
            "watsonx_available": bool(self.watsonx and self.watsonx.is_available),
            "watsonx_model": self.watsonx.model_id if self.watsonx else None,
            "groq_available": bool(self.groq and self.groq.is_available),
            "groq_model": self.groq.model_id if self.groq else None,
            "gemini_available": bool(self.gemini and self.gemini.is_available),
            "gemini_model": self.gemini.model_id if self.gemini else None,
            "chunk_size": self.chunk_size,
            "usage": _usage.to_dict(),
        }

_instance = None

def get_llm():
    global _instance
    if _instance is None:
        _instance = NexusLLM()
    return _instance

def get_llm_provider():
    return get_llm()
