"""Create the starter course if the database has none:  python -m scripts.seed"""
from app.db import SessionLocal
from app.seed import seed_default_course


def main() -> None:
    with SessionLocal() as db:
        course = seed_default_course(db)
    print(f"Created and activated: {course.title}" if course else "Courses already exist, nothing to do.")


if __name__ == "__main__":
    main()
