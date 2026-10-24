from pathlib import Path

backup_file = Path("trend_maturity_v2_backup.py")
target_file = Path("trend_maturity.py")

if not backup_file.exists():
    print("Error: Could not find trend_maturity_v2_backup.py")
    exit()

# Read the clean backup
lines = backup_file.read_text(encoding="utf-8").splitlines()

# Find the 'is_choppy' block, which we know exists in the backup
anchor_idx = -1
for i, line in enumerate(lines):
    if "is_choppy = (" in line:
        # Find the closing parenthesis of the is_choppy block
        for j in range(i, len(lines)):
            if ")" in lines[j]:
                anchor_idx = j
                break
        break

if anchor_idx == -1:
    print("Could not find the 'is_choppy' block in the backup.")
    exit()

# Determine the correct indentation (should be 8 spaces, inside the function)
indent = "        " # Default to 8 spaces

# Create the new block with PERFECT indentation
new_block = f"""{indent}
{indent}# ========================================
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

# Insert the block after the anchor
new_lines = lines[:anchor_idx+1] + [new_block] + lines[anchor_idx+1:]
target_file.write_text("\n".join(new_lines), encoding="utf-8")
print("[OK] Successfully patched trend_maturity.py from backup using 'is_choppy' anchor!")
