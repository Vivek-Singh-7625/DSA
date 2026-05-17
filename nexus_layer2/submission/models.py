"""
Nexus Layer 2 - Pydantic Models for CTG Ingestion
Validates and loads Layer 1 output for Neo4j ingestion
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import json
from pathlib import Path


class DPR(BaseModel):
    """Decision Provenance Record"""
    dpr_id: str
    title: str
    component: str
    within_window: bool
    decision_date: str
    decision: str
    rejected_alternatives: List[str]
    explicit_constraints: List[str]
    implicit_assumptions: List[str]
    intended_durability: str
    durability_reasoning: str
    causal_dependencies: List[str]
    files_involved: List[str]
    commit_refs: List[str]
    involved_humans: List[str]
    assumption_decay_risk: str
    decay_risk_reasoning: str
    blast_radius_estimate: str
    blast_radius_reasoning: str
    active_workarounds: List[str]


class CTGEdge(BaseModel):
    """Causal Temporal Graph Edge"""
    from_dpr: str
    to_dpr: str
    relationship: str
    explanation: str
    within_window: bool


class DecayAlert(BaseModel):
    """Assumption Decay Alert"""
    dpr_id: str
    assumption: str
    decay_signals_found: List[str]
    earliest_signal_date: str
    already_decaying: bool
    decay_evidence: str
    recommended_monitor_query: str


class NexusLayer1Metadata(BaseModel):
    """Metadata about the Layer 1 analysis"""
    repository: str
    analysis_window: str
    window_cutoff_date: str
    analysis_timestamp: str
    analysis_method: str
    focus_areas: List[str]
    total_dprs: int
    dprs_within_window: int
    dprs_pre_window_active: int


class NexusLayer1Output(BaseModel):
    """Complete Layer 1 output structure"""
    repository: str
    analysis_window: str
    window_cutoff_date: str
    analysis_timestamp: str
    analysis_method: str
    focus_areas: List[str]
    total_dprs: int
    dprs_within_window: int
    dprs_pre_window_active: int
    dprs: List[DPR]
    assumption_decay_prescan: List[DecayAlert]
    ctg_edges: List[CTGEdge]


class NexusLayer1Wrapper(BaseModel):
    """Wrapper for the JSON file structure"""
    nexus_layer1_output: NexusLayer1Output


def load_layer1(json_path: str = None) -> NexusLayer1Output:
    """
    Load and validate Layer 1 output from JSON file
    
    Args:
        json_path: Path to the Layer 1 JSON output file.
                   If None, auto-resolves relative to this script's directory.
        
    Returns:
        Validated NexusLayer1Output object
        
    Raises:
        FileNotFoundError: If JSON file doesn't exist
        ValidationError: If JSON doesn't match expected schema
    """
    if json_path is None:
        # Resolve relative to this script's parent (project root)
        script_dir = Path(__file__).resolve().parent
        project_root = script_dir.parent
        path = project_root / "postgres-analysis" / "output" / "nexus_layer1_dprs.json"
    else:
        path = Path(json_path)
    
    if not path.exists():
        # Also try relative to CWD
        alt_path = Path("postgres-analysis/output/nexus_layer1_dprs.json")
        if alt_path.exists():
            path = alt_path
        else:
            raise FileNotFoundError(
                f"Layer 1 output not found at: {path}\n"
                f"  Also tried: {alt_path.resolve()}"
            )
    
    print(f"📂 Loading Layer 1 output from: {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Validate against schema
    wrapper = NexusLayer1Wrapper(**data)
    output = wrapper.nexus_layer1_output
    
    # Print validation summary
    print("\n✅ VALIDATION SUCCESSFUL")
    print("=" * 60)
    print(f"Repository: {output.repository}")
    print(f"Analysis Window: {output.analysis_window}")
    print(f"Analysis Timestamp: {output.analysis_timestamp}")
    print(f"Focus Areas: {', '.join(output.focus_areas)}")
    print(f"\n📊 DATA SUMMARY:")
    print(f"  • Total DPRs: {output.total_dprs}")
    print(f"  • DPRs within window: {output.dprs_within_window}")
    print(f"  • DPRs pre-window (active): {output.dprs_pre_window_active}")
    print(f"  • CTG Edges: {len(output.ctg_edges)}")
    print(f"  • Decay Alerts: {len(output.assumption_decay_prescan)}")
    
    # Component breakdown
    components = {}
    for dpr in output.dprs:
        components[dpr.component] = components.get(dpr.component, 0) + 1
    
    print(f"\n🏗️  COMPONENTS:")
    for component, count in sorted(components.items()):
        print(f"  • {component}: {count} DPRs")
    
    # Risk breakdown
    blast_radius = {}
    decay_risk = {}
    for dpr in output.dprs:
        blast_radius[dpr.blast_radius_estimate] = blast_radius.get(dpr.blast_radius_estimate, 0) + 1
        decay_risk[dpr.assumption_decay_risk] = decay_risk.get(dpr.assumption_decay_risk, 0) + 1
    
    print(f"\n⚠️  BLAST RADIUS:")
    for level in ['critical', 'high', 'medium', 'low']:
        if level in blast_radius:
            print(f"  • {level.capitalize()}: {blast_radius[level]} DPRs")
    
    print(f"\n🔻 DECAY RISK:")
    for level in ['high', 'medium', 'low']:
        if level in decay_risk:
            print(f"  • {level.capitalize()}: {decay_risk[level]} DPRs")
    
    # Decay alerts breakdown
    already_decaying = sum(1 for alert in output.assumption_decay_prescan if alert.already_decaying)
    print(f"\n🚨 DECAY ALERTS:")
    print(f"  • Total alerts: {len(output.assumption_decay_prescan)}")
    print(f"  • Already decaying: {already_decaying}")
    print(f"  • Monitoring recommended: {len(output.assumption_decay_prescan) - already_decaying}")
    
    # Relationship types
    relationships = {}
    for edge in output.ctg_edges:
        relationships[edge.relationship] = relationships.get(edge.relationship, 0) + 1
    
    print(f"\n🔗 CTG RELATIONSHIPS:")
    for rel_type, count in sorted(relationships.items(), key=lambda x: x[1], reverse=True):
        print(f"  • {rel_type}: {count} edges")
    
    print("=" * 60)
    print("✅ Ready for Neo4j ingestion\n")
    
    return output


if __name__ == "__main__":
    """Test the models by loading the Layer 1 output"""
    try:
        output = load_layer1()
        print(f"✅ Successfully loaded and validated {output.total_dprs} DPRs")
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print("\n💡 Make sure the Layer 1 analysis has been run first:")
        print("   cd postgres-analysis")
        print("   ./nexus_layer1_analyzer.ps1")
    except Exception as e:
        print(f"❌ Validation error: {e}")
        import traceback
        traceback.print_exc()

# Made with Bob
