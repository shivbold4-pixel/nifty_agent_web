from pathlib import Path

print("=== 1. Patching config.yaml (Risk/Reward) ===")
p1 = Path("config.yaml")
if p1.exists():
    src1 = p1.read_text(encoding="utf-8")
    if "target_atr_mult: 1.0" in src1:
        src1 = src1.replace("target_atr_mult: 1.0", "target_atr_mult: 1.5")
        p1.write_text(src1, encoding="utf-8")
        print("[OK] config.yaml patched: Target is now 1.5x ATR (1:1 Risk/Reward).")
    else:
        print("[SKIP] config.yaml already patched or target not found.")
else:
    print("[ERROR] config.yaml not found.")

print("\n=== 2. Patching agent.py (Bearish Bias & Regime) ===")
p2 = Path("agent.py")
if p2.exists():
    src2 = p2.read_text(encoding="utf-8")
    
    # Fix the Bearish Bias (F01)
    old_wall = """            call_wall = float(df.nlargest(min(3, len(df)), "call_oi").strike.mean())
            put_wall = float(df.nlargest(min(3, len(df)), "put_oi").strike.mean())
            wall_asym = (put_wall - call_wall) / max(spot, 1)"""
            
    new_wall = """            call_wall = float(df.nlargest(min(3, len(df)), "call_oi").strike.mean())
            put_wall = float(df.nlargest(min(3, len(df)), "put_oi").strike.mean())
            # F01 FIX: Measure spot's position between the walls. Neutral = 0.0
            wall_range = max(call_wall - put_wall, 1.0)
            wall_asym = ((spot - put_wall) / wall_range) - 0.5"""
            
    if old_wall in src2:
        src2 = src2.replace(old_wall, new_wall)
        print("[OK] agent.py patched: Bearish bias cured.")
    else:
        print("[WARNING] Could not find exact wall_asym block.")

    # Fix the Regime Detector safety (F04)
    old_regime = """            self.regime_detector = RegimeDetector()
            self.tmf = TrendMaturityFilter()"""
            
    new_regime = """            self.regime_detector = RegimeDetector()
            self.vix = 0.0 # F04 FIX: Prevent AttributeError if vix is missing
            self.tmf = TrendMaturityFilter()"""
            
    if old_regime in src2:
        src2 = src2.replace(old_regime, new_regime)
        print("[OK] agent.py patched: Regime detector safety applied.")
    else:
        print("[WARNING] Could not find exact regime_detector block.")
        
    p2.write_text(src2, encoding="utf-8")
else:
    print("[ERROR] agent.py not found.")
