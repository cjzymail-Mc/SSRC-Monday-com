import argparse
import json
import os
from pathlib import Path

from flowboard.operations import apply_retention, create_backup, list_backups, restore_backup, verify_backup


def paths(args):
    db=Path(args.db or os.getenv("FLOWBOARD_DB","flowboard.db")).resolve();attachments=Path(args.attachments or os.getenv("FLOWBOARD_ATTACHMENT_DIR",db.parent/"flowboard-attachments")).resolve();backups=Path(args.backups or db.parent/"backups").resolve();return db,attachments,backups


def main():
    parser=argparse.ArgumentParser(description="Flowboard offline backup and restore operations")
    parser.add_argument("--db");parser.add_argument("--attachments");parser.add_argument("--backups");sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("backup");sub.add_parser("list");verify=sub.add_parser("verify");verify.add_argument("package");retention=sub.add_parser("retention");retention.add_argument("--keep",type=int,default=10);restore=sub.add_parser("restore");restore.add_argument("package")
    args=parser.parse_args();db,attachments,backups=paths(args)
    if args.command=="backup":result={"package":str(create_backup(db,attachments,backups))}
    elif args.command=="list":result={"backups":list_backups(backups)}
    elif args.command=="verify":result=verify_backup(args.package)
    elif args.command=="retention":result={"removed":apply_retention(backups,keep=args.keep)}
    else:result=restore_backup(args.package,db,attachments,safety_root=backups)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
