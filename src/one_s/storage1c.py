from datetime import datetime
from os import path, listdir, mkdir
from shutil import copyfile

from lxml import etree

from src.one_s.platform1c import Platform1C

# need to print debug message
DEBUG: bool = True


class Storage:
    """
    Work with 1C storage (repository)

    Attributes
    ----------
    platform : Platform1C
        platform used to connect to IB, linked with storage
    work_dir : str
        path to work dir
    build_path : str
        local path to catalog with releases
    net_path : str
        net path to catalog with releases
    prev_amount_cf : int
        amount of prev releases, which will in update file
    dump_path : str
        path to save configuration
    root_config_file : str
        full path to file Configuration.xml
    diff_file : str
        path fo save 1C diff-file, used in dump_to_files method
    objects_file : str
        path to file with information about 1C-storage objects
    repo_designer_params : list
        params to connect with 1C IB and with 1C storage
    log_designer_params : list
        params to write log file, for result of 1C Designer
    new_version : str
        new version representation
    cf_file : str
        path to generated cf file
    cfu_file : str
        path to generated cfu file
    config_name : str
        configuration name to find in root_config_file
    """
    build_path: str

    def __init__(self, work_dir: str, configuration: dict):
        self.platform = Platform1C('storage', configuration['platform_exe'])
        self.work_dir = work_dir
        self.build_path = configuration['build_path']
        self.net_path = configuration['net_path']
        self.prev_amount_cf = configuration['prev_amount_cf']
        self.dump_path = self.work_dir + '\\current_config'
        self.root_config_file = self.dump_path + '\\Configuration.xml'
        self.diff_file = self.work_dir + '\\diff.txt'
        self.objects_file = self.work_dir + '\\config_objects.xml'
        self.repo_designer_params = [
            '/s ' + configuration['ib_server'],
            '/N ' + configuration['ib_user'],
            '/ConfigurationRepositoryF ' + configuration['path'],
            '/ConfigurationRepositoryN ' + configuration['username'],
            '/ConfigurationRepositoryP ' + configuration['password']
        ]
        self.log_designer_params = ['/Out {}'.format(self.work_dir + '\\log.txt'), '-NoTruncate']
        self.new_version = None
        self.cf_file = None
        self.cfu_file = None
        self.config_name = configuration['config_name']

    def _designer(self, command: list) -> int:
        """
        Run 1C Designer to execute command

        :param command:
        :return:
        """
        start_time = datetime.now()
        designer_args = command
        designer_args.extend(self.log_designer_params)
        completed_process = self.platform.designer(self.repo_designer_params, designer_args)
        if DEBUG:
            print(completed_process)
        print('Execution time: {}'.format(datetime.now() - start_time))
        return completed_process.returncode

    def update_from_repo(self) -> int:
        """
        Update IB configuration from Storage

        :return:
        """
        result = self._designer(['/ConfigurationRepositoryUpdateCfg -force', '/UpdateDBCfg'])
        print('Update from Storage: {}'.format(result))
        return result

    def dump_to_files(self) -> int:
        """
        Dump configuration from IB to xml files

        :return:
        """
        params = ['/DumpConfigToFiles {}'.format(self.dump_path)]
        if path.exists(self.dump_path):
            print('Dump with update...')
            params.extend(['-update', '-force', '-getChanges {}'.format(self.diff_file)])
        result = self._designer(params)
        print('Dump Config: {}'.format(result))
        return result

    def lock_in_repo(self) -> int:
        """
        Lock objects in Repository

        :return:
        """
        result = self._designer(['/ConfigurationRepositoryLock', '-Objects {}'.format(self.objects_file)])
        print('Lock: {}'.format(result))
        return result

    def upgrade_version(self, next_release: bool = False) -> int:
        """
        Increase version of configuration

        :param next_release:
        :return:
        """
        # Меняем версию конфигурации в корневом файле Configuration.xml
        ns_md = '{http://v8.1c.ru/8.3/MDClasses}'
        config_xml = etree.parse(self.root_config_file)
        version_elems = config_xml.findall('./{ns}Configuration/{ns}Properties/{ns}Version'.format(ns=ns_md))
        if len(version_elems) == 0:
            print('Error while parse Configuration.xml')
            return 1
        current_version = version_elems[0].text
        self.new_version = _next_version(current_version, next_release)
        version_elems[0].text = self.new_version
        config_xml.write(self.root_config_file, encoding='utf-8', xml_declaration=True, pretty_print=True)
        # Меняем версию конфигурации в файле ConfigDumpInfo.xml
        ns_di = '{http://v8.1c.ru/8.3/xcf/dumpinfo}'
        _cdi_xml_file = self.dump_path + '\\ConfigDumpInfo.xml'
        xml_object = etree.parse(_cdi_xml_file)
        search_str = './{ns}ConfigVersions/{ns}Metadata[@name="Configuration.{config_name}"]'\
            .format(ns=ns_di, config_name=self.config_name)
        cdi_version_elems = xml_object.findall(search_str)
        if len(cdi_version_elems) == 0:
            print('Error while parse ConfigDumpInfo.xml')
            return 1
        orig_cv = cdi_version_elems[0].get('configVersion')
        orig_cv32 = orig_cv[0:32]
        cdi_version_elems[0].set('configVersion', orig_cv.replace(orig_cv32, orig_cv32[::-1]))
        xml_object.write(_cdi_xml_file, encoding='utf-8', xml_declaration=True, pretty_print=True)
        # Успех
        print('Upgrade from {} to {}'.format(current_version, self.new_version))
        return 0

    def load_from_files(self):
        """
        Load configuration to IB from xml-files

        :return:
        """
        params = ['/LoadConfigFromFiles {}'.format(self.dump_path), '-files {}'.format(self.root_config_file),
                  '-Format Hierarchical', '-updateConfigDumpInfo', '/UpdateDBCfg']
        result = self._designer(params)
        print('Upload config to storage: {}'.format(result))
        return result

    def commit_to_repo(self):
        """
        Commit changes to Repository

        :return:
        """
        if self.new_version is None:
            return 2
        params = ['/ConfigurationRepositoryCommit',  '-Objects {}'.format(self.objects_file),
                  '-comment', '{} - night build'.format(self.new_version)]
        result = self._designer(params)
        print('Commit: {}'.format(result))
        return result

    def make_build(self):
        """
        Make new build - cf and cfu files

        :return:
        """
        # Проверяем заполненность нужных параметров
        if self.new_version is None:
            return 2
        # Сформируем список кандидатов для обновления
        # Из каталога со сборками выбираем последние по дате изменения
        # Количество поставок для обновления задается в конфигурационном файле
        dirs_sorted = []
        dirs = listdir(self.build_path)
        for d in dirs:
            cur_path = self.build_path + '\\' + d
            if path.isdir(cur_path):
                dirs_sorted.append(tuple([d, path.getmtime(cur_path)]))
        dirs_sorted.sort(key=lambda tup: tup[1], reverse=True)
        # Сформируем параметры для запуска процесса создания файлов поставки
        cf_template = '{}\\{}\\1Cv8.cf'
        self.cf_file = cf_template.format(self.build_path, self.new_version)
        self.cfu_file = '{}\\{}\\1Cv8.cfu'.format(self.build_path, self.new_version)
        build_params = ['/CreateDistributionFiles', '-cffile ' + self.cf_file, '-cfufile ' + self.cfu_file]
        for x in dirs_sorted[:self.prev_amount_cf]:
            build_params.append('-f {}'.format(cf_template.format(self.build_path, x[0])))
        build_result = self._designer(build_params)
        print('Make build: {}'.format(build_result))
        return build_result

    def copy_ready_files(self):
        """Copy generated cf and cfu files to net

        :return:
        """
        # Скопируем файлы поставки на сетевой диск для общего использования
        nv_net_path = self.net_path + '\\' + self.new_version
        mkdir(nv_net_path)
        copyfile(self.cf_file, nv_net_path + '\\1Cv8.cf')
        copyfile(self.cfu_file, nv_net_path + '\\1Cv8.cfu')
        return 0

    def get_cfu_path(self) -> str:
        """Return a path to generated cfu file

        :return:
        """
        return self.cfu_file

    def make_new_version(self, next_release: bool = False) -> int:
        """
        General method for make new build, which encapsulate all work of this class

        :param next_release:
        :return:
        """
        # обновиться из хранилища
        if self.update_from_repo() > 0:
            return 1
        # выгрузить конфигурацию в файлы
        if self.dump_to_files() > 0:
            return 1
        # сохранить изменения в хранилище
        # 1) захватить корень конфигурации в хранилище
        if self.lock_in_repo() > 0:
            return 1
        # 2) повысить версию конфигурации
        if self.upgrade_version(next_release) > 0:
            # TODO: отпустить корень конфигурации
            return 1
        # 3) загрузить данные конфигурации из файла
        lc_result = self.load_from_files()
        # 4) поместить изменения в хранилище
        commit_result = self.commit_to_repo()
        if lc_result + commit_result > 0:
            print('Error before making build')
            return lc_result + commit_result
        # сделать файл поставки
        build_result = self.make_build()
        if build_result > 0:
            print('Error while making new build')
            return 1
        # скопировать файлы в сеть
        return self.copy_ready_files()


def _next_version(version, next_release: bool):
    """Increase version number

    :param version: current version needs to increase
    :param next_release: if True increase 3rd number, 4th otherwise
    :return: increased version
    """
    v_numbers = version.split('.')
    if len(v_numbers) == 4:
        if next_release:
            v_numbers[2] = str(int(v_numbers[2]) + 1)
            v_numbers[3] = '1'
        else:
            v_numbers[3] = str(int(v_numbers[3]) + 1)
        return '.'.join(v_numbers)
    return version
