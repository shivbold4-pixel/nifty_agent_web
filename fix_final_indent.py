from pathlib import Path

p = Path("auto_fetcher_v2.py")
if not p.exists():
    print("[ERROR] auto_fetcher_v2.py not found.")
    exit()

lines = p.read_text(encoding="utf-8").splitlines()

start_idx = -1
end_idx = -1

# Find the exact block
for i, line in enumerate(lines):
    if "# --- RISK MANAGER & CORRECT LABELING WIRE-UP ---" in line:
        start_idx = i
    if start_idx != -1 and '"realized_label": label})' in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    # Get the base indentation from the start comment line
    base_indent = lines[start_idx][:len(lines[start_idx]) - len(lines[start_idx].lstrip())]
    
    # Rebuild the block with perfect relative indentation
    new_block = [
        f"{base_indent}# --- RISK MANAGER & CORRECT LABELING WIRE-UP ---",
        f"{base_indent}direction = agent._pending.get(\"direction\", \"FLAT\")",
        f"{base_indent}points_moved = nifty - agent._pending[\"spot\"]",
        f"{base_indent}",
        f"{base_indent}# 1. Correct labeling based on direction",
        f"{base_indent}if direction == \"BULLISH\":",
        f"{base_indent}    label = 1 if realized_bps > 0 else 0",
        f"{base_indent}    mock_pnl = points_moved * 75 # Assuming 1 lot (75 qty)",
        f"{base_indent}elif direction == \"BEARISH\":",
        f"{base_indent}    label = 1 if realized_bps < 0 else 0",
        f"{base_indent}    mock_pnl = -points_moved * 75",
        f"{base_indent}else:",
        f"{base_indent}    label = 0",
        f"{base_indent}    mock_pnl = 0.0",
        f"{base_indent}",
        f"{base_indent}# 2. Feed the P&L to the Risk Manager",
        f"{base_indent}if mock_pnl != 0.0:",
        f"{base_indent}    agent.risk.register_trade(mock_pnl)",
        f"{base_indent}",
        f"{base_indent}sb_update(url, key, \"predictions\",",
        f"{base_indent}    where={{\"pred_ts\": agent._pending[\"ts\"]}},",
        f"{base_indent}    values={{\"outcome_bps\": round(realized_bps, 3),",
        f"{base_indent}            \"realized_label\": label}})"
    ]

    # Reconstruct the file
    new_lines = lines[:start_idx] + new_block + lines[end_idx+1:]
    p.write_text("\n".join(new_lines), encoding="utf-8")
    print("[OK] Indentation fixed! The Risk Manager block is now safely nested.")
else:
    print("[ERROR] Could not find the target block boundaries.")
