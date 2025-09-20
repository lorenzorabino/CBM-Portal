"""Simple link access control mapping by user role.

Edit NAV_ACCESS below to control which roles can see which nav links.
Valid roles: 'admin', 'planner', 'technician', 'guest' (not logged in)
"""

NAV_ACCESS = {
    # Main group
    'dashboard':     ['guest', 'technician', 'planner', 'admin'],
    'equipment':     ['guest', 'technician', 'planner', 'admin'],
    'testing':       ['guest', 'technician', 'planner', 'admin'],
    'validation':    ['guest', 'technician', 'planner', 'admin'],
    'reports':       ['guest','admin'],
    'calendar':      ['guest','planner', 'admin', 'technician'],
    'notifications': ['guest','planner', 'admin'],

    # Management group
    'technicians':   ['guest','technician', 'admin'],
    'planner':       ['guest','planner', 'admin'],
    'settings':      ['guest','admin'],
}
