from app.database import engine, Base, TaskView

def fix_db():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Done.")

if __name__ == "__main__":
    fix_db()
