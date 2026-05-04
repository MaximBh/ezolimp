"""
Full reset v2: clear ALL solution records and user stats.
Run from backend/ directory with venv: .venv\Scripts\python reset_viewed_flags.py
"""
import sys, os
sys.path.insert(0, '.')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Solution, UserStats, User

db = SessionLocal()
try:
    # 1. Delete ALL solution records
    sol_count = db.query(Solution).delete()
    print(f"1. Deleted {sol_count} solution records.")

    # 2. Reset all user stats to zero
    stats_count = db.query(UserStats).update({
        UserStats.total_solved: 0,
        UserStats.correct_answers: 0,
        UserStats.total_points: 0,
        UserStats.current_streak: 0,
        UserStats.best_streak: 0,
    })
    print(f"2. Reset stats for {stats_count} users.")

    # 3. Reset all user ratings to 1000
    rating_count = db.query(User).update({User.rating: 1000})
    print(f"3. Reset ratings for {rating_count} users.")

    db.commit()
    print("\nDone! All solution history, stats, and ratings have been cleared.")
    
    # Verify
    remaining = db.query(Solution).filter(Solution.viewed_solution == True).count()
    print(f"Verification: {remaining} records with viewed_solution=True (should be 0)")
except Exception as e:
    db.rollback()
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
