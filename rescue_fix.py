from pathlib import Path

backup_file = Path("trend_maturity_v2_backup.py")
target_file = Path("trend_maturity.py")

if not backup_file.exists():
    print("Error: Could not find trend_maturity_v2_backup.py")
    exit()

# Read the clean backup
lines = backup_file.read_text(encoding="utf-8").splitlines()

start_idx = -1
# Find the suppression block in the backup
for i, line in enumerate(lines):
    if "# SUPPRESSION FACTOR" in line:
        start_idx = i
        if i > 0 and "=" in lines[i-1]:
            start_idx = i - 1
        if i > 1 and "=" in lines[i-2]:
            start_idx = i - 2
        break

if start_idx == -1:
    print("Could not find the SUPPRESSION FACTOR block in the backup.")
    exit()

# Determine the correct indentation from the line above the block
indent = ""
for j in range(start_idx - 1, -1, -1):
    if lines[j].strip():
        indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
        break

# Create the new block with PERFECT indentation
new_block = f"""{indent}# ========================================
{indent}# SUPPRESSION FACTOR (v4 - VWAP slope aware)
{indent}# ========================================
{indent}# Calculate VWAP slope health
{indent}trend_up_healthy = vwap_slope > 0.0004 and overall_move > 0
{indent}trend_down_healthy = vwap_slope < -0.0004 and overall_move < 0
{indent}
{indent}if is_parabolic:
{indent}    suppression = 0.25
{indent}    state = 'PARABOLIC'
{indent}elif is_exhausted and not (trend_up_healthy or trend_down_healthy):
{indent}    suppression = 0.35
{indent}    state = 'EXHAUSTED'
{indent}elif is_exhausted and (trend_up_healthy or trend_down_healthy):
{indent}    # Trend is exhausted BUT VWAP is trending -> softer suppression
{indent}    suppression = 0.75
{indent}    state = 'TRENDING_EXTENDED'
{indent}elif is_healthy_trend:
{indent}    suppression = 1.0
{indent}    state = 'HEALTHY_TREND'
{indent}elif trend_up_healthy or trend_down_healthy:
{indent}    # VWAP confirms trend but TMF didn't flag as healthy
{indent}    suppression = 0.95
{indent}    state = 'TRENDING'
{indent}elif is_choppy:
{indent}    suppression = 0.6
{indent}    state = 'CHOPPY'
{indent}else:
{indent}    suppression = 0.85
{indent}    state = 'NEUTRAL'"""

# Find the end of the block in the backup
end_idx = -1
for i in range(start_idx, len(lines)):
    if "state = 'NEUTRAL'" in lines[i] or 'state = "NEUTRAL"' in lines[i]:
        end_idx = i
        break

if end_idx != -1:
    new_lines = lines[:start_idx] + [new_block] + lines[end_idx+1:]
    target_file.write_text("\n".join(new_lines), encoding="utf-8")
    print("[OK] Cleaned and patched trend_maturity.py successfully from backup!")
else:
    print("Could not find the end of the block in the backup.")
