from argparse import ArgumentParser as AP, RawDescriptionHelpFormatter
import atexit
import re
import sys

from . import __version__ as version

ap = AP(
    epilog="""

Examples:

    # Add new room 'xyz':
    python3 -msogs --add-room xyz --name 'XYZ Room'

    # Add 2 admins to each of rooms 'xyz' and 'abc':
    python3 -msogs --rooms abc xyz --admin --add-moderators 050123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef 0500112233445566778899aabbccddeeff00112233445566778899aabbccddeeff

     # Add a global moderator visible as a moderator of all rooms:
    python3 -msogs --add-moderators 050123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef --rooms=+ --visible

    # Set default read/write True and upload False on all rooms
    python3 -msogs --set-perms --add-perms rw --remove-perms u --rooms='*'

    # Remove overrides for user 0501234... on all rooms
    python3 -msogs --set-perms --clear-perms rwua --rooms='*' --users 050123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

     # List room info:
    python3 -msogs -L

A sogs.ini will be loaded from the current directory, if one exists.  You can override this by
specifying a path to the config file to load in the SOGS_CONFIG environment variable.

""",  # noqa: E501
    formatter_class=RawDescriptionHelpFormatter,
)

ap.add_argument('--version', '-V', action='version', version=f'PySOGS {version}')

actions = ap.add_mutually_exclusive_group(required=True)

actions.add_argument('--add-room', help="Add a room with the given token", metavar='TOKEN')
ap.add_argument(
    '--name', help="Set the room's initial name for --add-room; if omitted use the token name"
)
ap.add_argument('--description', help="Specifies the room's initial description for --add-room")
actions.add_argument('--delete-room', help="Delete the room with the given token", metavar='TOKEN')
actions.add_argument(
    '--add-moderators',
    nargs='+',
    metavar='SESSIONID',
    help="Add the given Session ID(s) as a moderator of the room given by --rooms",
)
actions.add_argument(
    '--delete-moderators',
    nargs='+',
    metavar='SESSIONID',
    help="Delete the the given Session ID(s) as moderator and admins of the room given by --rooms",
)
actions.add_argument(
    '--set-perms',
    action='store_true',
    help="Sets default or user-specific permissions for the room given by --rooms; specify the "
    "permissions using --add-perms or --remove-perms",
)
ap.add_argument(
    '--users',
    help="One or more specific users to set permissions for with --set-perms; if omitted then the "
    "room default permissions will be set for the given room(s) instead.",
    nargs='+',
    metavar='SESSIONID',
)
ap.add_argument(
    "--add-perms",
    help="With --add-room or --set-perms, set these permissions to true; takes a string of 1-4 of "
    "the letters \"rwua\" for [r]ead, [w]rite, [u]pload, and [a]ccess.",
)
ap.add_argument(
    "--remove-perms",
    help="With --add-room or --set-perms, set these permissions to false; takes the same string as "
    "--add-perms, but denies the listed permissions rather than granting them.",
)
ap.add_argument(
    "--clear-perms",
    help="With --add-room or --set-perms, clear room or user overrides on these permissions, "
    "returning them to the default setting.  Takes the same argument as --add-perms.",
)
ap.add_argument(
    '--admin',
    action='store_true',
    help="Add the given moderators as admins rather than ordinary moderators",
)
ap.add_argument(
    '--rooms',
    nargs='+',
    metavar='TOKEN',
    help="Room(s) to use when adding/removing moderators/admins or when setting permissions. "
    "If a single room name of '+' is given then the user will be added/removed as a global "
    "admin/moderator. '+' is not valid for setting permissions. If a single room name "
    "of '*' is given then the changes take effect on each of the server's current rooms.",
)
vis_group = ap.add_mutually_exclusive_group()
vis_group.add_argument(
    '--visible',
    action='store_true',
    help="Make an added moderator/admins' status publicly visible. This is the default for room "
    "mods, but not for global mods",
)
vis_group.add_argument(
    '--hidden',
    action='store_true',
    help="Hide the added moderator/admins' status from public users. This is the default for "
    "global mods, but not for room mods",
)
actions.add_argument(
    "--list-rooms", "-L", action='store_true', help="List current rooms and basic stats"
)
actions.add_argument(
    '--list-global-mods', '-M', action='store_true', help="List global moderators/admins"
)
ap.add_argument(
    "--verbose", "-v", action='store_true', help="Show more information for some commands"
)
ap.add_argument(
    "--yes", action='store_true', help="Don't prompt for confirmation for some commands, just do it"
)
actions.add_argument(
    "--initialize",
    action='store_true',
    help="Initialize database and private key if they do not exist; advanced use only.",
)
actions.add_argument(
    "--upgrade",
    "-U",
    action="store_true",
    help="Perform any required database upgrades.  If database upgrades are required then other "
    "commands will exit with an error message until this flag is used.  Note that this is "
    "normally not required: database upgrades are performed automatically during sogs daemon "
    "startup.",
)
actions.add_argument(
    "--check-upgrades",
    action="store_true",
    help="Check whether database upgrades are required then exit.  The exit code is 0 if no "
    "upgrades are needed, 5 if required upgrades were detected.",
)

args = ap.parse_args()

from . import config, crypto, db
from .migrations.exc import DatabaseUpgradeRequired
from sqlalchemy_utils import database_exists

db_updated = False
try:
    if not args.initialize and not database_exists(config.DB_URL):
        raise RuntimeError(f"{config.DB_URL} database does not exist")

    if args.initialize:
        crypto.persist_privkey()

    db.init_engine(sogs_skip_init=True)

    db_updated = db.database_init(create=args.initialize, upgrade=args.upgrade)

except DatabaseUpgradeRequired as e:
    print(
        f"Database upgrades are required: {e}\n\n"
        "You can attempt the upgrade using the --upgrade flag; see --help for details."
    )
    sys.exit(5)

except Exception as e:
    print(
        f"""

SOGS initialization failed: {e}.


Perhaps you need to specify a SOGS_CONFIG path or use one of the --upgrade/--initialize options?
Try --help for additional information.
"""
    )
    sys.exit(1)

from . import web
from .model.room import Room, get_rooms
from .model.user import User, SystemUser, get_all_global_moderators
from .model.exc import AlreadyExists, NoSuchRoom, NoSuchUser

web.appdb = db.get_conn()


@atexit.register
def close_conn():
    web.appdb.close()


def print_room(room: Room):
    msgs, msgs_size = room.messages_size()
    files, files_size = room.attachments_size()
    reactions = room.reactions_counts()
    r_total = sum(x[1] for x in reactions)
    reactions.sort(key=lambda x: x[1], reverse=True)

    msgs_size /= 1_000_000
    files_size /= 1_000_000

    active = [room.active_users_last(x * 86400) for x in (1, 7, 14, 30)]
    m, a, hm, ha = room.get_all_moderators()
    admins = len(a) + len(ha)
    mods = len(m) + len(hm)

    perms = "{}read, {}write, {}upload, {}accessible".format(
        "+" if room.default_read else "-",
        "+" if room.default_write else "-",
        "+" if room.default_upload else "-",
        "+" if room.default_accessible else "-",
    )

    print(
        f"""
{room.token}
{"=" * len(room.token)}
Name: {room.name}
Description: {room.description}
URL: {config.URL_BASE}/{room.token}?public_key={crypto.server_pubkey_hex}
Messages: {msgs} ({msgs_size:.1f} MB)
Attachments: {files} ({files_size:.1f} MB)
Reactions: {r_total}; top 5: {', '.join(f"{r} ({c})" for r, c in reactions[0:5])}
Active users: {active[0]} (1d), {active[1]} (7d), {active[2]} (14d), {active[3]} (30d)
Default permissions: {perms}
Moderators: {admins} admins ({len(ha)} hidden), {mods} moderators ({len(hm)} hidden)""",
        end='',
    )
    if args.verbose and any((m, a, hm, ha)):
        print(":")
        for id in a:
            print(f"    - {id} (admin)")
        for id in ha:
            print(f"    - {id} (hidden admin)")
        for id in m:
            print(f"    - {id} (moderator)")
        for id in hm:
            print(f"    - {id} (hidden moderator)")
    else:
        print()


def room_token_valid(room):
    if not re.fullmatch(r'[\w-]{1,64}', room):
        print(
            "Error: room tokens may only contain a-z, A-Z, 0-9, _, and - characters",
            file=sys.stderr,
        )
        sys.exit(1)


def perm_flag_to_word(char):
    if char == 'r':
        return "read"
    if char == 'w':
        return "write"
    if char == 'u':
        return "upload"
    if char == 'a':
        return "accessible"

    print(f"Error: invalid permission flag '{char}'")
    sys.exit(1)


perms = {}


def parse_and_set_perm_flags(flags, perm_setting):
    for char in flags:
        perm_type = perm_flag_to_word(char)
        if perm_type in perms:
            print(
                f"Error: permission flag '{char}' in more than one permission set "
                "(add/remove/clear)"
            )
            sys.exit(1)
        perms[perm_type] = perm_setting


if args.add_room or args.set_perms:
    if args.add_perms:
        parse_and_set_perm_flags(args.add_perms, True)
    if args.remove_perms:
        parse_and_set_perm_flags(args.remove_perms, False)
    if args.clear_perms:
        parse_and_set_perm_flags(args.clear_perms, None)

if args.initialize:
    print("Database schema created.")

elif args.upgrade:
    print("Database successfully upgraded." if db_updated else "No database upgrades required.")

elif args.check_upgrades:
    print("No database upgrades required.")

elif args.add_room:
    room_token_valid(args.add_room)

    try:
        room = Room.create(
            token=args.add_room, name=args.name or args.add_room, description=args.description
        )
        if "read" in perms:
            room.default_read = perms["read"]
        if "write" in perms:
            room.default_write = perms["write"]
        if "accessible" in perms:
            room.default_accessible = perms["accessible"]
        if "upload" in perms:
            room.default_upload = perms["upload"]

    except AlreadyExists:
        print(f"Error: room '{args.add_room}' already exists!", file=sys.stderr)
        sys.exit(1)
    print(f"Created room {args.add_room}:")
    print_room(room)

elif args.delete_room:
    try:
        room = Room(token=args.delete_room)
    except NoSuchRoom:
        print(f"Error: no such room '{args.delete_room}'", file=sys.stderr)
        sys.exit(1)

    print_room(room)
    if args.yes:
        res = "y"
    else:
        res = input("Are you sure you want to delete this room? [yN] ")
    if res.startswith("y") or res.startswith("Y"):
        room.delete()
        print("Room deleted.")
    else:
        print("Aborted.")
        sys.exit(2)

elif args.add_moderators:
    if not args.rooms:
        print("Error: --rooms is required when using --add-moderators", file=sys.stderr)
        sys.exit(1)
    for a in args.add_moderators:
        if not re.fullmatch(r'[01]5[A-Fa-f0-9]{64}', a):
            print(f"Error: '{a}' is not a valid session id", file=sys.stderr)
            sys.exit(1)
    if len(args.rooms) > 1 and ('*' in args.rooms or '+' in args.rooms):
        print(
            "Error: '+'/'*' arguments to --rooms cannot be used with other rooms", file=sys.stderr
        )
        sys.exit(1)

    sysadmin = SystemUser()

    if args.rooms == ['+']:
        for sid in args.add_moderators:
            u = User(session_id=sid, try_blinding=True)
            u.set_moderator(admin=args.admin, visible=args.visible, added_by=sysadmin)
            print(
                "Added {} as {} global {}".format(
                    sid,
                    "visible" if args.visible else "hidden",
                    "admin" if args.admin else "moderator",
                )
            )
    else:
        if args.rooms == ['*']:
            rooms = get_rooms()
        else:
            try:
                rooms = [Room(token=r) for r in args.rooms]
            except NoSuchRoom as nsr:
                print(f"No such room: '{nsr.token}'", file=sys.stderr)
                sys.exit(1)

        for sid in args.add_moderators:
            u = User(session_id=sid, try_blinding=True)
            for room in rooms:
                room.set_moderator(u, admin=args.admin, visible=not args.hidden, added_by=sysadmin)
                print(
                    "Added {} as {} {} of {} ({})".format(
                        u.session_id,
                        "hidden" if args.hidden else "visible",
                        "admin" if args.admin else "moderator",
                        room.name,
                        room.token,
                    )
                )

elif args.delete_moderators:
    if not args.rooms:
        print("Error: --rooms is required when using --delete-moderators", file=sys.stderr)
        sys.exit(1)
    for a in args.delete_moderators:
        if not re.fullmatch(r'[01]5[A-Fa-f0-9]{64}', a):
            print(f"Error: '{a}' is not a valid session id", file=sys.stderr)
            sys.exit(1)
    if len(args.rooms) > 1 and ('*' in args.rooms or '+' in args.rooms):
        print(
            "Error: '+'/'*' arguments to --rooms cannot be used with other rooms", file=sys.stderr
        )
        sys.exit(1)

    sysadmin = SystemUser()

    if args.rooms == ['+']:
        for sid in args.delete_moderators:
            u = User(session_id=sid, try_blinding=True)
            was_admin = u.global_admin
            if not u.global_admin and not u.global_moderator:
                print(f"{u.session_id} was not a global moderator")
            else:
                u.remove_moderator(removed_by=sysadmin)
                print(f"Removed {u.session_id} as global {'admin' if was_admin else 'moderator'}")

            if u.is_blinded and sid.startswith('05'):
                try:
                    u2 = User(session_id=sid, try_blinding=False, autovivify=False)
                    if u2.global_admin or u2.global_moderator:
                        was_admin = u2.global_admin
                        u2.remove_moderator(removed_by=sysadmin)
                        print(
                            f"Removed {u2.session_id} as global "
                            f"{'admin' if was_admin else 'moderator'}"
                        )
                except NoSuchUser:
                    pass
    else:
        if args.rooms == ['*']:
            rooms = get_rooms()
        else:
            try:
                rooms = [Room(token=r) for r in args.rooms]
            except NoSuchRoom as nsr:
                print(f"No such room: '{nsr.token}'", file=sys.stderr)

        for sid in args.delete_moderators:
            u = User(session_id=sid, try_blinding=True)
            u2 = None
            if u.is_blinded and sid.startswith('05'):
                try:
                    u2 = User(session_id=sid, try_blinding=False, autovivify=False)
                except NoSuchUser:
                    pass

            for room in rooms:
                room.remove_moderator(u, removed_by=sysadmin)
                print(f"Removed {u.session_id} as moderator/admin of {room.name} ({room.token})")
                if u2 is not None:
                    room.remove_moderator(u2, removed_by=sysadmin)
                    print(
                        f"Removed {u2.session_id} as moderator/admin of {room.name} ({room.token})"
                    )

elif args.set_perms:
    if not args.rooms:
        print("Error: --rooms is required when using --set-perms", file=sys.stderr)
        sys.exit(1)

    if args.rooms == ['+']:
        print("Error: --rooms cannot be '+' (i.e. global) with --set-perms", file=sys.stderr)
        sys.exit(1)

    users = []
    if args.users:
        users = [User(session_id=sid, try_blinding=True) for sid in args.users]

    rooms = []
    if args.rooms == ['*']:
        rooms = get_rooms()
    else:
        try:
            rooms = [Room(token=r) for r in args.rooms]
        except NoSuchRoom as nsr:
            print(f"No such room: '{nsr.token}'", file=sys.stderr)

    if not len(rooms):
        print("Error: no valid rooms specified for call to --set-perms")
        sys.exit(1)

    # users not specified means set room defaults
    if not len(users):
        for room in rooms:
            if "read" in perms:
                room.default_read = perms["read"]
            if "write" in perms:
                room.default_write = perms["write"]
            if "accessible" in perms:
                room.default_accessible = perms["accessible"]
            if "upload" in perms:
                room.default_upload = perms["upload"]
    else:
        sysadmin = SystemUser()
        for room in rooms:
            for user in users:
                room.set_permissions(user, mod=sysadmin, **perms)

elif args.list_rooms:
    rooms = get_rooms()
    if rooms:
        for room in rooms:
            print_room(room)
    else:
        print("No rooms.")

elif args.list_global_mods:
    m, a, hm, ha = get_all_global_moderators()
    admins = len(a) + len(ha)
    mods = len(m) + len(hm)

    print(f"{admins} global admins ({len(ha)} hidden), {mods} moderators ({len(hm)} hidden):")
    for u in a:
        print(f"- {u.session_id} (admin)")
    for u in ha:
        print(f"- {u.session_id} (hidden admin)")
    for u in m:
        print(f"- {u.session_id} (moderator)")
    for u in hm:
        print(f"- {u.session_id} (hidden moderator)")

else:
    print("Error: no action given", file=sys.stderr)
    ap.print_usage()
    sys.exit(1)
