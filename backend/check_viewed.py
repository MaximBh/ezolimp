"""Check which users have viewed_solution=True records"""
import sys
sys.path.insert(0, '.')

from app.database import SessionLocal, Solution, User

db = SessionLocal()
try:
    viewed = db.query(Solution).filter(Solution.viewed_solution == True).all()
    if not viewed:
        print("No records with viewed_solution=True found.")
    else:
        print(f"Found {len(viewed)} records with viewed_solution=True:")
        for sol in viewed:
            user = db.query(User).filter(User.id == sol.user_id).first()
            uname = user.username if user else "unknown"
            print(f"  user_id={sol.user_id} ({uname}), task_id={sol.task_id}, is_correct={sol.is_correct}")
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
