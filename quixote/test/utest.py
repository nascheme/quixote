# Minimal class to make old Sancho tests work with py.test.
import types

class UTest:
    def __init__(self):
        print('Running %s:' % self.__class__.__name__)
        for name in dir(self):
            # Find all methods starting with check_, call them.
            if name.startswith('check_'):
                method = getattr(self, name)
                if isinstance(method, types.MethodType):
                    print('  ', name)
                    method()
