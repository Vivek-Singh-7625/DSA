"""
Nexus — GPU Accelerator Module
Leverages NVIDIA RTX 3050 (CUDA) for compute-heavy graph analytics:
  - Graph centrality calculations
  - Blast radius matrix computation
  - Embedding similarity search (cosine sim on GPU)
  - Batch risk scoring

Falls back gracefully to CPU (NumPy/NetworkX) when CUDA is unavailable.

Environment Variables:
  NEXUS_USE_GPU    — "true" (default) | "false" to force CPU
  CUDA_DEVICE      — GPU device index (default: 0)
"""

import os
import sys
import time
import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ── GPU Detection — Force NVIDIA RTX, skip Intel iGPU ─────
HAS_TORCH = False
HAS_CUDA = False
GPU_NAME = "N/A"
GPU_MEMORY_MB = 0
_SELECTED_CUDA_IDX = 0

def _select_rtx_device():
    """Enumerate CUDA devices, skip Intel, select NVIDIA RTX."""
    global _SELECTED_CUDA_IDX
    import torch
    n = torch.cuda.device_count()
    print(f"[GPU] Found {n} CUDA device(s)")
    for i in range(n):
        name = torch.cuda.get_device_name(i)
        mem = torch.cuda.get_device_properties(i).total_mem // (1024 * 1024)
        print(f"  [{i}] {name} ({mem} MB)")
        # Skip Intel integrated GPUs
        if "intel" in name.lower():
            print(f"  [{i}] SKIPPED — Intel iGPU not suitable for compute")
            continue
        # Prefer RTX / NVIDIA
        if "nvidia" in name.lower() or "rtx" in name.lower() or "gtx" in name.lower() or "geforce" in name.lower():
            _SELECTED_CUDA_IDX = i
            os.environ["CUDA_VISIBLE_DEVICES"] = str(i)
            os.environ["CUDA_DEVICE"] = str(i)
            print(f"  [+] Selected GPU [{i}]: {name} ({mem} MB) — NVIDIA RTX")
            return i, name, mem
    # Fallback: use first non-Intel device, or device 0
    for i in range(n):
        name = torch.cuda.get_device_name(i)
        if "intel" not in name.lower():
            _SELECTED_CUDA_IDX = i
            os.environ["CUDA_VISIBLE_DEVICES"] = str(i)
            return i, name, torch.cuda.get_device_properties(i).total_mem // (1024*1024)
    # Last resort: device 0
    return 0, torch.cuda.get_device_name(0), torch.cuda.get_device_properties(0).total_mem // (1024*1024)

try:
    import torch
    HAS_TORCH = True
    if torch.cuda.is_available():
        HAS_CUDA = True
        _SELECTED_CUDA_IDX, GPU_NAME, GPU_MEMORY_MB = _select_rtx_device()
    else:
        print("[GPU] CUDA not available — using CPU fallback")
except ImportError:
    print("[GPU] PyTorch not installed — using CPU fallback")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False


def use_gpu() -> bool:
    """Check if GPU should be used."""
    forced = os.environ.get("NEXUS_USE_GPU", "true").lower()
    return HAS_CUDA and forced != "false"


def get_device():
    """Get the torch device — always the selected NVIDIA RTX device."""
    if use_gpu():
        return torch.device(f"cuda:{_SELECTED_CUDA_IDX}")
    elif HAS_TORCH:
        return torch.device("cpu")
    return None


def gpu_status() -> dict:
    """Return GPU status for API reporting."""
    info = {
        "torch_installed": HAS_TORCH,
        "cuda_available": HAS_CUDA,
        "gpu_active": use_gpu(),
        "gpu_name": GPU_NAME,
        "gpu_memory_mb": GPU_MEMORY_MB,
        "device": str(get_device()) if HAS_TORCH else "cpu",
    }
    if HAS_CUDA:
        try:
            info["gpu_memory_used_mb"] = torch.cuda.memory_allocated() // (1024 * 1024)
            info["gpu_memory_cached_mb"] = torch.cuda.memory_reserved() // (1024 * 1024)
            info["gpu_utilization"] = "active"
        except Exception:
            pass
    return info


# ═══════════════════════════════════════════════════════════
# GPU-ACCELERATED GRAPH ANALYTICS
# ═══════════════════════════════════════════════════════════

class GPUGraphAnalyzer:
    """
    GPU-accelerated graph analysis using CUDA tensors.
    Falls back to NetworkX on CPU when GPU is unavailable.
    """

    def __init__(self, dprs: List[dict], edges: List[dict]):
        self.dprs = dprs
        self.edges = edges
        self.device = get_device()
        self.dpr_ids = [d.get("id", d.get("dpr_id", "")) for d in dprs]
        self.id_to_idx = {did: i for i, did in enumerate(self.dpr_ids)}
        self.n = len(dprs)

        # Build adjacency matrix
        self.adj_matrix = self._build_adjacency_matrix()

        # Risk weight vectors
        self.blast_weights = self._build_weight_vector("blast_radius",
            {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0})
        self.decay_weights = self._build_weight_vector("decay_risk",
            {"high": 3.0, "medium": 2.0, "low": 1.0})

    def _build_adjacency_matrix(self):
        """Build adjacency matrix — GPU tensor or numpy array."""
        if use_gpu():
            adj = torch.zeros((self.n, self.n), dtype=torch.float32, device=self.device)
            for e in self.edges:
                fr = e.get("from", e.get("from_dpr", ""))
                to = e.get("to", e.get("to_dpr", ""))
                if fr in self.id_to_idx and to in self.id_to_idx:
                    adj[self.id_to_idx[fr], self.id_to_idx[to]] = 1.0
            return adj
        elif HAS_NUMPY:
            adj = np.zeros((self.n, self.n), dtype=np.float32)
            for e in self.edges:
                fr = e.get("from", e.get("from_dpr", ""))
                to = e.get("to", e.get("to_dpr", ""))
                if fr in self.id_to_idx and to in self.id_to_idx:
                    adj[self.id_to_idx[fr], self.id_to_idx[to]] = 1.0
            return adj
        return None

    def _build_weight_vector(self, field: str, mapping: dict):
        """Build a weight vector from DPR field values."""
        default = 1.0
        weights = []
        for d in self.dprs:
            val = d.get(field, d.get(f"{field}_estimate", "medium"))
            weights.append(mapping.get(val, default))

        if use_gpu():
            return torch.tensor(weights, dtype=torch.float32, device=self.device)
        elif HAS_NUMPY:
            return np.array(weights, dtype=np.float32)
        return weights

    def compute_reachability_matrix(self):
        """
        GPU-accelerated transitive closure via matrix exponentiation.
        Finds all reachable nodes from each node using repeated matrix multiply.
        """
        if self.adj_matrix is None or self.n == 0:
            return None

        t0 = time.time()

        if use_gpu():
            # GPU path: matrix power for transitive closure
            reach = self.adj_matrix.clone()
            power = self.adj_matrix.clone()
            for _ in range(min(self.n, 20)):  # cap iterations
                power = torch.mm(power, self.adj_matrix)
                reach = reach + power
                if torch.all(reach > 0):
                    break
            reach = (reach > 0).float()
            backend = "CUDA/RTX 3050"
        else:
            # CPU path with numpy
            reach = self.adj_matrix.copy()
            power = self.adj_matrix.copy()
            for _ in range(min(self.n, 20)):
                power = np.dot(power, self.adj_matrix)
                reach = reach + power
                if np.all(reach > 0):
                    break
            reach = (reach > 0).astype(np.float32)
            backend = "CPU/NumPy"

        elapsed = time.time() - t0
        print(f"  [GPU] Reachability matrix ({self.n}×{self.n}) computed in "
              f"{elapsed*1000:.1f}ms [{backend}]")
        return reach

    def compute_blast_radius_scores(self) -> List[dict]:
        """
        Compute weighted blast radius for every DPR using GPU matrix ops.
        Score = number_of_reachable_nodes × avg_blast_weight_of_reachable
        """
        reach = self.compute_reachability_matrix()
        if reach is None:
            return []

        t0 = time.time()
        results = []

        if use_gpu():
            # GPU: vectorized blast radius
            reach_counts = reach.sum(dim=1)   # how many nodes each can reach
            # Weighted reach: multiply reachability by blast weights
            weighted = torch.mm(reach, self.blast_weights.unsqueeze(1)).squeeze()
            total_weight = self.blast_weights.sum()
            normalized = weighted / max(total_weight.item(), 1.0)

            for i, dpr_id in enumerate(self.dpr_ids):
                downstream = int(reach_counts[i].item())
                score = round(normalized[i].item(), 4)
                downstream_ids = [self.dpr_ids[j] for j in range(self.n)
                                  if reach[i, j].item() > 0]
                results.append({
                    "dpr_id": dpr_id,
                    "blast_radius_count": downstream,
                    "blast_radius_score": score,
                    "blast_radius_dpr_ids": downstream_ids,
                })
        else:
            # CPU fallback
            reach_counts = reach.sum(axis=1)
            weighted = np.dot(reach, self.blast_weights)
            total_weight = self.blast_weights.sum()
            normalized = weighted / max(total_weight, 1.0)

            for i, dpr_id in enumerate(self.dpr_ids):
                downstream = int(reach_counts[i])
                score = round(float(normalized[i]), 4)
                downstream_ids = [self.dpr_ids[j] for j in range(self.n)
                                  if reach[i, j] > 0]
                results.append({
                    "dpr_id": dpr_id,
                    "blast_radius_count": downstream,
                    "blast_radius_score": score,
                    "blast_radius_dpr_ids": downstream_ids,
                })

        elapsed = time.time() - t0
        print(f"  [GPU] Blast radius scores for {len(results)} DPRs: {elapsed*1000:.1f}ms")
        return results

    def compute_composite_risk_scores(self) -> List[dict]:
        """
        GPU-accelerated composite risk scoring.
        Combines blast radius, decay risk, connectivity, and workaround count.
        """
        reach = self.compute_reachability_matrix()
        if reach is None:
            return []

        t0 = time.time()
        results = []

        if use_gpu():
            reach_counts = reach.sum(dim=1)
            in_degree = self.adj_matrix.sum(dim=0)
            out_degree = self.adj_matrix.sum(dim=1)
            connectivity = in_degree + out_degree

            # Workaround penalty vector
            wa_counts = torch.tensor(
                [len(d.get("active_workarounds", [])) for d in self.dprs],
                dtype=torch.float32, device=self.device
            )

            # Composite: 35% blast + 25% decay + 20% connectivity + 20% workarounds
            max_reach = max(reach_counts.max().item(), 1.0)
            max_conn = max(connectivity.max().item(), 1.0)
            max_wa = max(wa_counts.max().item(), 1.0)

            composite = (
                0.35 * (self.blast_weights / 4.0) +
                0.25 * (self.decay_weights / 3.0) +
                0.20 * (connectivity / max_conn) +
                0.20 * (wa_counts / max_wa)
            ) * 100

            for i, dpr_id in enumerate(self.dpr_ids):
                results.append({
                    "dpr_id": dpr_id,
                    "composite_risk": round(composite[i].item(), 1),
                    "blast_component": round(self.blast_weights[i].item() / 4.0 * 100, 1),
                    "decay_component": round(self.decay_weights[i].item() / 3.0 * 100, 1),
                    "connectivity_component": round(connectivity[i].item() / max_conn * 100, 1),
                    "workaround_component": round(wa_counts[i].item() / max_wa * 100, 1),
                    "downstream_count": int(reach_counts[i].item()),
                })
        else:
            # CPU fallback
            reach_counts = reach.sum(axis=1) if HAS_NUMPY else [0] * self.n
            in_degree = self.adj_matrix.sum(axis=0) if HAS_NUMPY else [0] * self.n
            out_degree = self.adj_matrix.sum(axis=1) if HAS_NUMPY else [0] * self.n
            connectivity = in_degree + out_degree if HAS_NUMPY else [0] * self.n

            wa_counts = np.array(
                [len(d.get("active_workarounds", [])) for d in self.dprs],
                dtype=np.float32
            ) if HAS_NUMPY else [0] * self.n

            max_reach = max(float(max(reach_counts)) if HAS_NUMPY else 1, 1.0)
            max_conn = max(float(max(connectivity)) if HAS_NUMPY else 1, 1.0)
            max_wa = max(float(max(wa_counts)) if HAS_NUMPY else 1, 1.0)

            for i, dpr_id in enumerate(self.dpr_ids):
                bw = float(self.blast_weights[i]) if HAS_NUMPY else 2.0
                dw = float(self.decay_weights[i]) if HAS_NUMPY else 1.0
                cn = float(connectivity[i]) if HAS_NUMPY else 0
                wa = float(wa_counts[i]) if HAS_NUMPY else 0
                rc = float(reach_counts[i]) if HAS_NUMPY else 0

                composite = (
                    0.35 * (bw / 4.0) +
                    0.25 * (dw / 3.0) +
                    0.20 * (cn / max_conn) +
                    0.20 * (wa / max_wa)
                ) * 100

                results.append({
                    "dpr_id": dpr_id,
                    "composite_risk": round(composite, 1),
                    "blast_component": round(bw / 4.0 * 100, 1),
                    "decay_component": round(dw / 3.0 * 100, 1),
                    "connectivity_component": round(cn / max_conn * 100, 1),
                    "workaround_component": round(wa / max_wa * 100, 1),
                    "downstream_count": int(rc),
                })

        results.sort(key=lambda x: x["composite_risk"], reverse=True)
        elapsed = time.time() - t0
        backend = "CUDA/RTX 3050" if use_gpu() else "CPU"
        print(f"  [GPU] Composite risk scores: {elapsed*1000:.1f}ms [{backend}]")
        return results

    def compute_centrality(self) -> List[dict]:
        """
        GPU-accelerated PageRank-style centrality.
        Uses power iteration on the adjacency matrix.
        """
        if self.adj_matrix is None or self.n == 0:
            return []

        t0 = time.time()
        damping = 0.85
        iterations = 50
        tol = 1e-6

        if use_gpu():
            # Normalize adjacency matrix columns
            col_sums = self.adj_matrix.sum(dim=0)
            col_sums = torch.where(col_sums == 0, torch.ones_like(col_sums), col_sums)
            M = self.adj_matrix / col_sums.unsqueeze(0)

            # Power iteration
            rank = torch.ones(self.n, dtype=torch.float32, device=self.device) / self.n
            teleport = torch.ones(self.n, dtype=torch.float32, device=self.device) / self.n

            for _ in range(iterations):
                new_rank = damping * torch.mv(M, rank) + (1 - damping) * teleport
                if torch.norm(new_rank - rank) < tol:
                    break
                rank = new_rank

            rank = rank / rank.sum()  # normalize
            results = []
            for i, dpr_id in enumerate(self.dpr_ids):
                results.append({
                    "dpr_id": dpr_id,
                    "centrality": round(rank[i].item(), 6),
                })
        else:
            # CPU/NetworkX fallback
            if HAS_NX:
                G = nx.DiGraph()
                for e in self.edges:
                    fr = e.get("from", e.get("from_dpr", ""))
                    to = e.get("to", e.get("to_dpr", ""))
                    G.add_edge(fr, to)
                pr = nx.pagerank(G, alpha=damping)
                results = [{"dpr_id": did, "centrality": round(pr.get(did, 0), 6)}
                           for did in self.dpr_ids]
            else:
                results = [{"dpr_id": did, "centrality": round(1.0 / self.n, 6)}
                           for did in self.dpr_ids]

        results.sort(key=lambda x: x["centrality"], reverse=True)
        elapsed = time.time() - t0
        backend = "CUDA/RTX 3050" if use_gpu() else "CPU"
        print(f"  [GPU] Centrality (PageRank) computed: {elapsed*1000:.1f}ms [{backend}]")
        return results

    def compute_similarity_matrix(self, embeddings: List[List[float]] = None):
        """
        GPU-accelerated cosine similarity between DPR text embeddings.
        If no embeddings provided, uses a simple bag-of-words TF vector.
        """
        if self.n == 0:
            return None

        t0 = time.time()

        if embeddings is None:
            # Build simple TF vectors from DPR text
            all_words = set()
            texts = []
            for d in self.dprs:
                words = set()
                for field in ["title", "decision", "component"]:
                    for w in d.get(field, "").lower().split():
                        words.add(w)
                        all_words.add(w)
                for a in d.get("implicit_assumptions", []):
                    for w in a.lower().split():
                        words.add(w)
                        all_words.add(w)
                texts.append(words)

            word_list = sorted(all_words)
            word_idx = {w: i for i, w in enumerate(word_list)}
            dim = len(word_list)

            if use_gpu():
                vecs = torch.zeros((self.n, dim), dtype=torch.float32, device=self.device)
                for i, words in enumerate(texts):
                    for w in words:
                        if w in word_idx:
                            vecs[i, word_idx[w]] = 1.0
            elif HAS_NUMPY:
                vecs = np.zeros((self.n, dim), dtype=np.float32)
                for i, words in enumerate(texts):
                    for w in words:
                        if w in word_idx:
                            vecs[i, word_idx[w]] = 1.0
            else:
                return None
        else:
            if use_gpu():
                vecs = torch.tensor(embeddings, dtype=torch.float32, device=self.device)
            elif HAS_NUMPY:
                vecs = np.array(embeddings, dtype=np.float32)
            else:
                return None

        # Cosine similarity
        if use_gpu():
            norms = torch.norm(vecs, dim=1, keepdim=True)
            norms = torch.where(norms == 0, torch.ones_like(norms), norms)
            normalized = vecs / norms
            sim_matrix = torch.mm(normalized, normalized.t())
            result = sim_matrix.cpu().numpy().tolist()
        elif HAS_NUMPY:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1.0, norms)
            normalized = vecs / norms
            sim_matrix = np.dot(normalized, normalized.T)
            result = sim_matrix.tolist()
        else:
            return None

        elapsed = time.time() - t0
        backend = "CUDA/RTX 3050" if use_gpu() else "CPU"
        print(f"  [GPU] Similarity matrix ({self.n}×{self.n}): {elapsed*1000:.1f}ms [{backend}]")
        return result


# ── Convenience Functions ─────────────────────────────────

def gpu_blast_radius(dprs: List[dict], edges: List[dict]) -> List[dict]:
    """Quick GPU blast radius computation."""
    analyzer = GPUGraphAnalyzer(dprs, edges)
    return analyzer.compute_blast_radius_scores()


def gpu_risk_scores(dprs: List[dict], edges: List[dict]) -> List[dict]:
    """Quick GPU composite risk scoring."""
    analyzer = GPUGraphAnalyzer(dprs, edges)
    return analyzer.compute_composite_risk_scores()


def gpu_centrality(dprs: List[dict], edges: List[dict]) -> List[dict]:
    """Quick GPU centrality computation."""
    analyzer = GPUGraphAnalyzer(dprs, edges)
    return analyzer.compute_centrality()


def gpu_benchmark(n: int = 50) -> dict:
    """Run a quick GPU benchmark to verify CUDA acceleration."""
    t0 = time.time()
    result = {
        "gpu_available": HAS_CUDA,
        "gpu_name": GPU_NAME,
        "gpu_memory_mb": GPU_MEMORY_MB,
        "matrix_size": n,
    }

    if use_gpu():
        # Matrix multiply benchmark
        a = torch.randn(n, n, device=get_device())
        b = torch.randn(n, n, device=get_device())
        torch.cuda.synchronize()
        t1 = time.time()
        for _ in range(100):
            c = torch.mm(a, b)
        torch.cuda.synchronize()
        gpu_time = time.time() - t1

        # CPU comparison
        a_cpu = a.cpu()
        b_cpu = b.cpu()
        t2 = time.time()
        for _ in range(100):
            c_cpu = torch.mm(a_cpu, b_cpu)
        cpu_time = time.time() - t2

        result["gpu_matmul_100x_ms"] = round(gpu_time * 1000, 2)
        result["cpu_matmul_100x_ms"] = round(cpu_time * 1000, 2)
        result["speedup"] = round(cpu_time / max(gpu_time, 0.001), 2)
        result["backend"] = "CUDA/RTX 3050"
    else:
        result["backend"] = "CPU"
        result["note"] = "CUDA not available, using CPU fallback"

    result["total_ms"] = round((time.time() - t0) * 1000, 2)
    return result
