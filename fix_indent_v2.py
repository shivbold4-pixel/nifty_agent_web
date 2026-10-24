from pathlib import Path
import textwrap

p = Path("trend_maturity.py")
if not p.exists():
    print("File not found.")
    exit()

lines = p.read_text(encoding="utf-8").splitlines()

start_idx = -1
end_idx = -1

# 1. Find the start of the block
for i, line in enumerate(lines):
    if "# SUPPRESSION FACTOR" in line:
        start_idx = i
        if i > 0 and "=" in lines[i-1]:
            start_idx = i - 1
        if i > 1 and "=" in lines[i-2]:
            start_idx = i - 2
        break

# 2. Find the end of the block
if start_idx != -1:
    for i in range(start_idx, len(lines)):
        if "state = 'NEUTRAL'" in lines[i] or 'state = "NEUTRAL"' in lines[i]:
            end_idx = i
            break

# 3. Fix the indentation properly
if start_idx != -1 and end_idx != -1:
    # Determine the correct base indentation from the line above the block
    indent = ""
    for j in range(start_idx - 1, -1, -1):
        if lines[j].strip():
            indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
            break
    
    # Create the base block with correct internal relative indentation
    base_block = """# ========================================
# SUPPRESSION FACTOR (v4 - VWAP slope aware)
# ========================================
if is_parabolic:
    suppression = 0.25
    state = 'PARABOLIC'
elif is_exhausted and not (trend_up_healthy or trend_down_healthy):
    suppression = 0.35
    state = 'EXHAUSTED'
elif is_exhausted and (trend_up_healthy or trend_down_healthy):
    # Trend is exhausted BUT VWAP is trending -> softer suppression
    suppression = 0.75
    state = 'TRENDING_EXTENDED'
elif is_healthy_trend:
    suppression = 1.0
    state = 'HEALTHY_TREND'
elif trend_up_healthy or trend_down_healthy:
    # VWAP confirms trend but TMF didn't flag as healthy
    suppression = 0.95
    state = 'TRENDING'
elif is_choppy:
    suppression = 0.6
    state = 'CHOPPY'
else:
    suppression = 0.85
    state = 'NEUTRAL'"""
    
    # Dedent the block (removes the 4 spaces we put in the string) and apply the correct outer indent
    new_block = textwrap.indent(textwrap.dedent(base_block), indent)
    
    # Reconstruct the file
    new_lines = lines[:start_idx] + [new_block] + lines[end_idx+1:]
    p.write_text("\n".join(new_lines), encoding="utf-8")
    print(f"[OK] Indentation fixed successfully with base indent: {repr(indent)}")
else:
    print("[SKIP] Could not find start or end of block.")
