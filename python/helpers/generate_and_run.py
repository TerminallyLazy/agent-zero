import json  
import re  
import subprocess  
import textwrap  
from pathlib import Path  
import sys  
from typing import List, Tuple  
import pandas as pd  
from python.helpers.files import get_abs_path  
import models  
  
# Replace the direct OpenAI usage with Agent Zero's model system  
def _chat_and_extract(*, prompt: str, model_config, temperature: float) -> Tuple[str, str]:  
    """Return (thoughts, python_code) from one chat completion using Agent Zero's model system."""  
      
    system_msg = """Answer with two fenced blocks: first ```thoughts, then ```python, nothing else.  
  
When analyzing data, prioritize preserving domain expertise and insights in your visualizations:  
1. Make visualizations that illuminate the domain context, not just show the data  
2. Include annotations that highlight key domain insights  
3. Use titles and comments that emphasize the domain-specific findings  
4. Ensure the narrative in your thoughts connects the visualizations to the original domain insights  
  
Visualization Best Practices:  
- Legends should be clear, descriptive, and properly positioned  
- Use appropriate color schemes (colorblind-friendly)  
- When plotting multiple data series, use proper techniques to avoid overwriting  
- Prepare data properly before visualization (aggregation, transformation)  
- Include appropriate sizing and formatting for all visual elements"""  
  
    # Ensure we're getting a CHAT model, not an embedding model  
    model = models.get_model(  
        type=models.ModelType.CHAT,  # Force CHAT type  
        provider=model_config.provider,  
        name=model_config.name,  
        **model_config.kwargs  
    )  
      
    from langchain_core.messages import SystemMessage, HumanMessage  
    messages = [SystemMessage(content=system_msg), HumanMessage(content=prompt)]  
      
    response = model.invoke(messages)  
    content = response.content  
      
    thoughts_m = re.search(r"```thoughts(.*?)```", content, re.S)  
    code_m = re.search(r"```python(.*?)```", content, re.S)  
    if not (thoughts_m and code_m):  
        raise ValueError("Model response missing required fenced blocks.")  
    return thoughts_m.group(1).strip(), code_m.group(1).strip()
  
def generate_analysis(  
    csv_path: str | Path,  
    insight_json_path: str | Path,  
    *,  
    model_config=None,  
    temperature: float = 0.2,  
    run_code: bool = True,  
    save_dir: str | Path = ".",  
    preserve_domain_insights: bool = True,  
) -> str:  
    """Generate Tree-of-Thought rationale and plotting script using Agent Zero's model system."""  
      
    # Use Agent Zero's file path handling  
    csv_path = Path(get_abs_path(str(csv_path)))  
    insight_json_path = Path(get_abs_path(str(insight_json_path)))  
    save_dir = Path(get_abs_path(str(save_dir)))  
    save_dir.mkdir(parents=True, exist_ok=True)  
  
    if not csv_path.exists():  
        raise FileNotFoundError(csv_path)  
    if not insight_json_path.exists():  
        raise FileNotFoundError(insight_json_path)  
  
    # Load assets  
    insight_json_str = insight_json_path.read_text(encoding="utf-8")  
    insights_obj = json.loads(insight_json_str)  
  
    df_full = pd.read_csv(csv_path)  
    schema_table = "\n".join(f"- {c}: {t}" for c, t in df_full.dtypes.items())  
  
    # Extract descriptive/predictive/domain-related texts  
    insight_texts: List[str] = [  
        insights_obj.get("descriptive", ""),  
        insights_obj.get("predictive", ""),  
        insights_obj.get("domain_related", ""),  
    ]  
      
    # Add emphasis on domain insights if requested  
    if preserve_domain_insights and insights_obj.get("domain_related"):  
        system_guidance = """IMPORTANT: The domain_related insights contain critical context that MUST be preserved   
and highlighted in your visualizations. Do not reduce the analysis to just chart selection -   
ensure the domain expertise is reflected in annotations, titles, and the narrative."""  
    else:  
        system_guidance = ""  
  
    # Build Tree-of-Thought blocks  
    TOT_BLOCK = """  
### Insight to Visualise and Interpret  
{INSIGHT_TEXT}  
  
### Three‑Expert Tree of Thought  
  
**Step I – Extract Key Domain Findings**    
Experts identify the core domain insights that need visual representation:

Expert 1: [Domain finding 1]
Expert 2: [Domain finding 2]
Expert 3: [Domain finding 3]

  
**Step II – Identify Relevant Data**    
Each expert independently lists dataframe columns they think support the insight.  

Expert 1: ['colA', 'colB', 'colC-B']
Expert 2: ['colB', 'colC']
Expert 3: ['colA', 'colC', 'colD+C', 'colE/A', 'colF-B']

  
**Step III – Evaluate Data Selection**    
Experts compare lists and agree on the minimal set.  

Agreed columns: ['colA', 'colB']

  
**Step IV – Visualise with Domain Context**    
Each expert proposes a chart type and explains how it highlights domain insights:  

Expert 1: Bar chart - Shows investment preference patterns while highlighting the shift toward digital platforms
Expert 2: Trend line - Visualizes age-based patterns, supporting the prediction about retirement planning shifts
Expert 3: Stacked bar - Reveals demographic segments' behavior, illuminating the financial literacy variations

  
**Consolidation**    
Output final decisions:  

Final chart: [chart type]
Reason: [visualization rationale]
Key insight narrative: [1-2 sentences explaining what domain insight this visualization helps reveal]
Recommended annotation: [Specific callout/annotation that should be added to highlight the domain insight]

"""  
  
    tot_blocks = "\n\n".join(  
        TOT_BLOCK.replace("{INSIGHT_TEXT}", txt.strip() or "(missing)")  
        for txt in insight_texts if txt.strip()  
    )  
  
    # Build the main prompt  
    PROMPT_TEMPLATE = """  
You are an elite data‑visualisation consultant.  
  
Context:  
  • **insight_library** (JSON):  
{insight_json}  
  • **CSV_SCHEMA** (column → dtype):  
{schema_table}  
  • **CSV_PATH** – a string pointing to the dataset on disk.  
  
Below, you will see one or more *Tree‑of‑Thought* blocks.  Follow the  
instructions inside each block to reason step‑by‑step and decide on a  
single chart for every insight.  
  
{TOT_BLOCKS}  
  
Return **exactly two fenced blocks** in order and nothing else:  
  
1️⃣ Thoughts block (label it ```thoughts) – include your full reasoning.  
  
2️⃣ Python block (label it ```python) – write a script that:  
   • imports pandas as pd, matplotlib.pyplot as plt, numpy as np, Path  
   • reads dataset via CSV_PATH (already defined)  
   • implements each **Final chart** decision  
   • includes comments explaining the domain insights for each visualization  
   • adds appropriate titles, labels, and annotations that highlight the key insights  
   • wraps every plot in try/except (KeyError, ValueError, TypeError) and `print()` a warning  
     if skipped  
   • calls plt.tight_layout(); show() or save to figures/  
   • uses **only** columns listed in CSV_SCHEMA.  
  
   Visualization Best Practices:  
   • For legends: Always use clear, descriptive legend titles and place them optimally (usually upper right or outside)  
   • For color selection: Use colorblind-friendly palettes (viridis, plasma, cividis) or plt.cm.Paired  
   • For multiple series: When plotting multiple data series, either:  
     - Use plt.subplots to create separate plots, or  
     - Use proper stacking techniques with stacked=True parameter  
     - Avoid overwriting plots on the same axes unless showing direct comparisons  
   • For pie charts: Use plt.axis('equal') to ensure proper circular appearance  
   • For data preparation: Use pandas aggregation (crosstab, pivot_table) before plotting  
   • For formatting: Set appropriate fontsize for title (14), labels (12), and tick labels (10)  
"""  
  
    prompt = PROMPT_TEMPLATE.format(  
        insight_json=insight_json_str,  
        schema_table=schema_table,  
        TOT_BLOCKS=tot_blocks,  
    )  
      
    if preserve_domain_insights:  
        prompt = system_guidance + "\n\n" + prompt  
  
    # Use Agent Zero's model system with LiteLLM integration  
    thoughts, code_body = _chat_and_extract(  
        prompt=prompt,  
        model_config=model_config,  
        temperature=temperature,  
    )  
  
    # Write artifacts  
    thoughts_file = save_dir / "analysis_thoughts.md"  
    code_file = save_dir / "analysis.py"  
  
    thoughts_file.write_text(thoughts, encoding="utf-8")  
  
    # Inject CSV_PATH as a Path object and ensure the generated code  
    # actually *uses* it instead of a placeholder literal.  
    header = textwrap.dedent(  
        f"""# Auto‑generated by generate_analysis  
from pathlib import Path  
CSV_PATH = Path(r"{csv_path}")  
  
# Auto‑generated by generate_analysis  
"""  
    )  
  
    # Fix common path issues in generated code  
    code_fixed = re.sub(  
        r"pd\.read_csv\(['\"].*?(\.csv|\.CSV|path_to_your_dataset\.csv)['\"].*?\)",  
        "pd.read_csv(CSV_PATH)",  
        code_body,  
        flags=re.I,  
    )  
  
    # Also check for any other direct string references to CSV files  
    code_fixed = re.sub(  
        r"['\"].*?path_to_your_dataset\.csv['\"]",  
        "CSV_PATH",  
        code_fixed,  
        flags=re.I,  
    )  
      
    # Handle direct assignment to CSV_PATH with a hardcoded path  
    code_fixed = re.sub(  
        r"CSV_PATH\s*=\s*['\"].*?(\.csv|\.CSV|path/to/your/dataset\.csv)['\"]",  
        "# CSV_PATH is defined above",  
        code_fixed,  
        flags=re.I,  
    )  
  
    # Create a figures directory if any plots will be saved there  
    figures_dir = save_dir / "figures"  
    figures_dir.mkdir(parents=True, exist_ok=True)  
  
    code_file.write_text(header + "\n" + code_fixed, encoding="utf-8")  
  
    print(f"🧠  Thoughts saved → {thoughts_file}")  
    print(f"📊  Analysis code → {code_file}")  
  
    if run_code:  
        print("🚀  Executing generated analysis script…")  
          
        # Verify the CSV file exists before trying to run the code  
        if not csv_path.exists():  
            print(f"⚠️  Warning: CSV file not found at {csv_path}")  
            print("⚠️  Script execution skipped.")  
            return thoughts  
              
        try:  
            subprocess.run([sys.executable, str(code_file)], check=True)  
        except subprocess.CalledProcessError as e:  
            print(f"⚠️  Error executing analysis script: {e}")  
            print("⚠️  Check the generated code for issues.")  
              
    return thoughts  
