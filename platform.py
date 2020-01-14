import subprocess


class Platform1C:
    """
    Shell over subprocess, can run 1C in Enterprise or Designer mode

    Attributes
    ----------
    name : str
        short name for 1C platform version
    exe_path : str
        path to client exe-file
    shell_mode : bool
        need to run subprocess in shell mode
    """

    def __init__(self, name: str, exe_path: str, shell_mode: bool = False):
        self.name = name
        self.exe_path = exe_path
        self.shell_mode = shell_mode

    def _run(self, run_type: str, conn_args: list, args: list = None):
        """Run 1C in run_type mode for IB in conn_args with args

        :param run_type:
        :param conn_args:
        :param args:
        :return:
        """
        if not self.shell_mode:
            run_args = [self.exe_path, run_type]
            run_args.extend(conn_args)
            if args is not None:
                run_args.extend(args)
            return subprocess.run(run_args)
        else:
            args_str = ' '.join(args) if args is not None else ''
            return subprocess.run([self.exe_path, '{} {} {}'.format(run_type, ' '.join(conn_args), args_str)],
                                  shell=True)

    def designer(self, conn_args, args):
        """Run 1C Designer for IB in conn_args with args

        :param conn_args:
        :param args:
        :return:
        """
        return self._run('DESIGNER', conn_args, args)

    def enterprise(self, conn_args, args=None):
        """Run 1C Enterprise for IB in conn_args with args

        :param conn_args:
        :param args:
        :return:
        """
        return self._run('ENTERPRISE', conn_args, args)


class BaseInfo:
    """
    Connection to concrete 1C-IB for update configuration

    Attributes
    ----------
    name : str
        name of this IB
    platform : Platform1C
        platform which used to run this IB
    server : str
        server address
    user : str
        username
    password : str
        password
    """

    def __init__(self, name, platform: Platform1C, server: str, user: str, password: str):
        self.name = name
        self.platform = platform
        self.server = server
        self.user = user
        self.password = password
        self.base_conn_args = ['/s ' + self.server, '/N ' + self.user]
        if self.password:
            self.base_conn_args.append('/P ' + self.password)

    def update(self, update_file: str):
        """Run update process - designer, when enterprise

        :return: None
        """
        designer_args = ['/UpdateCfg', update_file, '/UpdateDBCfg', '-Dynamic+']
        designer_process = self.platform.designer(self.base_conn_args, designer_args)
        print('Designer step done for base {}, return code: {}'.format(self.name, designer_process.returncode))
        enterprise_process = self.platform.enterprise(self.base_conn_args, [])
        print('Enterprise step done for base {}, return code: {}'.format(self.name, enterprise_process.returncode))
