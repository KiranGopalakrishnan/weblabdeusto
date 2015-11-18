# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
import threading
import requests
from selenium import webdriver
from selenium.webdriver import FirefoxProfile
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import NoAlertPresentException
import unittest, time, re

import os
from test.util import ports
from voodoo.gen import load_dir
from voodoo.gen.registry import GLOBAL_REGISTRY



class TimeoutError(Exception):
    def __init__(self):
        pass

class TestWeblabInstanceRunner(threading.Thread):
    """
    Class to manage the running of the selenium test weblab instance.
    TODO: The WebLab instance is at the moment never stopped.
    TODO: More things.
    """

    def __init__(self):
        threading.Thread.__init__(self)

        self.global_config = None
        self.core_server_url = None
        self.handler = None

    def _start_weblab(self):
        """
        Starts the instance and blocks while it is alive.
        It may take a while to actually start. You can check whether it is ready to
        process requests through is_ready.

        Meant to be called from the spawned thread.
        :return:
        """

        # Load the configuration of the weblab instance that we have set up for just this test.
        self.global_config = load_dir('test/deployments/selenium_tests')

        # Override the port so that we can start & close it fast enough.
        port = ports.new()
        self.core_server_url = 'http://127.0.0.1:{0}/weblab/'.format(port)
        # TODO: The following two lines to modify the port currently do not work.
        # But they should.
        self.global_config['myhost']['myprocess']['mycore'].config_values['core_facade_port'] = port
        self.global_config['myhost']['myprocess']['mycore'].config_values[
            'core_server_url'] = self.core_server_url

        # Start the weblab instance. The dont-start flag is set to False, so this call
        # WILL BLOCK and start the HTTP server.
        self.handler = self.global_config.load_process('myhost', 'myprocess')

    def is_ready(self):
        """
        Checks whether the instance has been started and is ready to reply.
        :rtype bool: Whether it is ready or not.
        :return:
        """
        if self.core_server_url is None:
            return False

        finished = False
        try:
            r = requests.get('{0}json/'.format(self.core_server_url), allow_redirects=False)
            if r.status_code == 200:
                finished = True
        except:
            pass

        return finished

    def wait_until_ready(self, timeout):
        """
        Waits (blocking) until the WebLab instance responds, or until the timeout expires. If the timeout
        expires without being ready a TimeoutError exception is thrown.
        :param timeout: Number of seconds to wait at most.
        :raises TimeoutError: In case of timeout.
        :return:
        """
        # Wait until we are ready.
        began = time.time()
        while True:
            if time.time() - began >= timeout:
                raise TimeoutError()
            if self.is_ready():
                print("[DBG]: Instance is ready")
                break
            else:
                # print("[DBG]: Instance not ready yet")
                pass

            time.sleep(0.5)

    def run(self):
        try:
            self._start_weblab()
        except:
            print("[ERROR]: Failed to start WebLab Test Instance")
            raise

class SeleniumBaseTest(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(SeleniumBaseTest, self).__init__(*args, **kwargs)
        pass

    def test_empty(self):
        pass

    def setUp(self):
        """
        Start a weblab instance for the test.
        :return:
        """
        print("Setup")

        self.weblab_instance_runner = TestWeblabInstanceRunner()
        self.weblab_instance_runner.start()
        self.weblab_instance_runner.wait_until_ready(10)

    @classmethod
    def setUpClass(cls):
        pass
        # if os.environ.get("SELENIUM_HEADLESS") and False:
        #     self.driver = webdriver.PhantomJS()
        # else:
        #     self.profile = FirefoxProfile()
        #     self.profile.set_preference("intl.accept_languages", "en")
        #     self.driver = webdriver.Firefox(self.profile)
        #
        # self.driver.set_window_size(1400, 1000)
        #
        # # self.driver.implicitly_wait(30)
        #
        # # TODO:
        # self.port = ports.new()
        # self.base_url = "http://localhost:{0}/".format(ports.new())
        # self.verificationErrors = []
        # self.accept_next_alert = True

    def is_element_present(self, how, what):
        try:
            self.driver.find_element(by=how, value=what)
        except NoSuchElementException, e:
            return False
        return True

    def is_alert_present(self):
        try:
            self.driver.switch_to_alert()
        except NoAlertPresentException, e:
            return False
        return True

    def close_alert_and_get_its_text(self):
        try:
            alert = self.driver.switch_to_alert()
            alert_text = alert.text
            if self.accept_next_alert:
                alert.accept()
            else:
                alert.dismiss()
            return alert_text
        finally:
            self.accept_next_alert = True


    def tearDown(self):
        pass

    @classmethod
    def tearDownClass(cls):
        pass
        #self.driver.quit()
        #self.assertEqual([], self.verificationErrors)


if __name__ == "__main__":
    unittest.main()
