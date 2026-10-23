"""Build-only v2 domain/commitment adapter; saved pair engine stays byte-identical."""
from ._frozen import bind
bind(globals(), 'sdk_alpha/build.py', [
    ("DOMAIN = 'DEVELOPER_SAVED_PAIR03'", "DOMAIN = 'DEVELOPER_SAVED_PAIR03_V2'", 1),
    ('Domain:"DEVELOPER_SAVED_PAIR03",', 'Domain:"DEVELOPER_SAVED_PAIR03_V2",', 1),
    ('func(x *portableAuthority){x.Domain="PORTABLE_SAVED_PAIR03"},',
     'func(x *portableAuthority){x.Domain="PORTABLE_SAVED_PAIR03"},func(x *portableAuthority){x.Domain="DEVELOPER_SAVED_PAIR03"},', 1),
])
