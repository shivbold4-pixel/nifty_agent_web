from pathlib import Path

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
        # Include the ===== line above it if it exists
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

# 3. Fix the indentation
if start_idx != -1 and end_idx != -1:
    # Determine the correct indentation from the line above
    indent = ""
    for j in range(start_idx - 1, -1, -1):
        if lines[j].strip():  # Find the first non-empty line
            indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
            break
    
    # Extract the block, strip existing indentation, and apply the correct one
    block = lines[start_idx:end_idx+1]
    block = [line.lstrip() for line in block]
    new_block = [indent + line for line in block]
    
    # Reconstruct the file
    new_lines = lines[:start_idx] + new_block + lines[end_idx+1:]
    p.write_text("\n".join(new_lines), encoding="utf-8")
    print("[OK] Indentation fixed successfully.")
else:
    print("[SKIP] Could not find start or end of block.")
