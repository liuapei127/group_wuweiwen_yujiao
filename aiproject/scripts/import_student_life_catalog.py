"""Import reviewed guides into an explicitly selected database, without automatic DDL."""
import argparse,json
from pathlib import Path
from sqlalchemy import text
from app.core.config import get_settings
from app.core.database import SessionLocal


def allowed_source(row, existing_url):
    allowed = {row["source_url"]}
    previous = row.get("previous_source_url")
    if isinstance(previous, str) and previous.startswith("https://"):
        allowed.add(previous)
    return existing_url in allowed


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--database",required=True)
    args=parser.parse_args()
    if args.database!=get_settings().db_name:
        parser.error("Configured database does not match explicit target")
    rows=json.loads((Path(__file__).resolve().parents[1]/"docs/student-workspace/overseas-life-catalog.json").read_text(encoding="utf-8"))
    with SessionLocal() as db:
        for row in rows:
            assert len(row["details"]["faqs"])>=3 and row["source_url"].startswith("https://")
            values={**row,"old_title":row.get("previous_title",row["title"]),"details":json.dumps(row["details"],ensure_ascii=False)}
            found=db.execute(text("SELECT id,source_url FROM overseas_life_knowledge WHERE country=:country AND (title=:title OR title=:old_title) FOR UPDATE"),values).mappings().one_or_none()
            if found and not allowed_source(row, found["source_url"]):
                raise RuntimeError("Existing guide has a different source; review before replacing")
            if found:
                db.execute(text("UPDATE overseas_life_knowledge SET title=:title,content=:content,category=:category,city=:city,source_title=:source_title,source_url=:source_url,details=:details,verified_at=:verified_at,update_time=NOW() WHERE id=:id"),{**values,"id":found["id"]})
            else:
                db.execute(text("INSERT INTO overseas_life_knowledge(country,category,title,content,city,source_title,source_url,details,verified_at,status,create_time,update_time) VALUES(:country,:category,:title,:content,:city,:source_title,:source_url,:details,:verified_at,1,NOW(),NOW())"),values)
        db.commit()
    print("Reviewed guides imported:",len(rows),"articles;",sum(len(row["details"]["faqs"]) for row in rows),"questions")


if __name__=="__main__":
    main()
