# pylint: disable=locally-disabled, multiple-statements, fixme, line-too-long, wrong-import-order, too-many-locals, unused-import, unused-wildcard-import, logging-fstring-interpolation, broad-exception-caught, wildcard-import, ungrouped-imports, invalid_name, bare-except, trailing-whitespace, unused-variable
# pyright: reportOperatorIssue=false, reportOptionalSubscript=false, reportArgumentType=false

from asyncio import exceptions
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.alert import Alert
# from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.keys import Keys  # Add this import
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

import json
import logging
import time
from datetime import datetime, timedelta
import re
import os
import random
from dotenv import load_dotenv
import pandas as pd
from config import Config

load_dotenv()

PROFILE_PATH = os.getenv('PROFILE_PATH')
TESTING = bool(os.getenv('TESTING', 'False')=='True')

PROFILE_DATA = Config('data/profile.json').load_profile()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
LLM_APPLIER = None

BROWSER="CHROME" # FIREFOX

class ColoredFormatter(logging.Formatter):
    """
    This class handles the coloring of log statements where color is supported on the console.
    """
    COLORS = {
        'DEBUG': '\033[0m',
        'INFO': '\033[94m',
        'WARNING': '\033[93m',
        'ERROR': '\033[91m',
        'CRITICAL': '\033[95m'
    }
    RESET = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        message = super().format(record)
        return f"{log_color}{message}{self.RESET}"

formatter = ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %H:%M:%S')
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger('__name__')
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)


def safe_send_keys(driver, xpath, text, max_retries=3):
    """
    Safely send keys to an element with retry logic and stale element handling
    
    Args:
        driver: WebDriver instance
        xpath: XPath to locate the element
        text: Text to send to the element
        max_retries: Maximum number of retry attempts
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Original approach as final fallback
    for attempt in range(max_retries):
        try:
            # Add small wait and then find element directly
            wait_here(0.5, 1)
            element = driver.find_element(By.XPATH, xpath)
            
            # Multiple scrolling attempts with different strategies
            scroll_attempts = [
                # Strategy 1: Smooth scroll to center
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                # Strategy 2: Instant scroll to center
                "arguments[0].scrollIntoView({block: 'center'});",
                # Strategy 3: Scroll to top of element
                "arguments[0].scrollIntoView(true);",
                # Strategy 4: Manual scroll with offset
                "window.scrollTo(0, arguments[0].offsetTop - window.innerHeight / 2);"
            ]
            
            scrolled = False
            for scroll_script in scroll_attempts:
                try:
                    driver.execute_script(scroll_script, element)
                    wait_here(0.8, 1.2)  # Wait for scroll to complete
                    
                    # Check if element is now in viewport
                    is_in_viewport = driver.execute_script(
                        "var rect = arguments[0].getBoundingClientRect(); "
                        "return (rect.top >= 0 && rect.left >= 0 && "
                        "rect.bottom <= window.innerHeight && rect.right <= window.innerWidth);",
                        element
                    )
                    
                    if is_in_viewport:
                        scrolled = True
                        break
                except Exception as scroll_error:
                    logger.warning(f"Scroll attempt failed: {scroll_error}")
                    continue
            
            if not scrolled:
                logger.warning(f"Could not scroll element into view after multiple attempts: {xpath}")
            
            # Try to make element interactable
            try:
                # Wait for element to be clickable
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
            except TimeoutException:
                # If element is not clickable, try to focus it with JavaScript
                try:
                    driver.execute_script("arguments[0].focus();", element)
                    wait_here(0.3, 0.5)
                except Exception as focus_error:
                    logger.warning(f"Could not focus element: {focus_error}")
            
            # Clear the field first
            try:
                element.clear()
            except Exception:
                # If clear fails, try JavaScript approach
                driver.execute_script("arguments[0].value = '';", element)
            
            # Send the text
            element.send_keys(text)
            
            logger.info(f"Successfully sent keys to element: {xpath}")
            return True
            
        except StaleElementReferenceException:
            logger.warning(f"Stale element reference on attempt {attempt + 1}, retrying...")
            wait_here(1, 2)
            continue
        except Exception as e:
            logger.error(f"Error sending keys on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                return False
            wait_here(1, 2)
            continue
    
    return False


def wait_here(min_, max_):
    """
    For waiting
    """
    # Convert float inputs to integers to avoid randint error
    min_int = int(min_)
    max_int = int(max_)
    wait_time = random.randint(min_int, max_int)
    if wait_time > 10:
        logger.info(f"Waiting for {wait_time} seconds...")
    time.sleep(wait_time)


def wait_for_page_loading(driver, wait_count=60):
    """
    Page stuck at loading
    """
    while driver.find_elements(By.XPATH, '//div[@data-automation-id="loading"]'):
        logger.info("Page is loading, waiting...")
        wait_here(3, 5)
        wait_count -= 1
        if wait_count <= 0:
            print("Page stuck at loading")
            return False

    return True


def make_options():
    """
    Makes options for Selenium driver with basic stealth
    """
    if BROWSER == "FIREFOX":
        options = webdriver.FirefoxOptions()
    else:
        options = webdriver.ChromeOptions()
    
    try:
        if BROWSER == "FIREFOX":
            # Create Firefox profile with proper cookie settings
            profile = webdriver.FirefoxProfile(PROFILE_PATH)
            # profile = webdriver.ChromeProfile()
            
            # Core cookie preferences
            profile.set_preference("network.cookie.cookieBehavior", 0)
            profile.set_preference("network.cookie.lifetimePolicy", 0)
            profile.set_preference("privacy.clearOnShutdown.cookies", False)
            profile.set_preference("privacy.clearOnShutdown.sessions", False)
            profile.set_preference("browser.privatebrowsing.autostart", False)
            profile.set_preference("dom.storage.enabled", True)
            profile.set_preference("browser.sessionstore.enabled", True)

            # === BASIC STEALTH - Hide automation indicators ===

            # Hide WebDriver presence (most important)
            profile.set_preference("dom.webdriver.enabled", False)
            profile.set_preference("useAutomationExtension", False)
            
            # Disable marionette (Firefox's automation protocol)
            profile.set_preference("marionette.enabled", False)
            
            # Set a normal user agent
            profile.set_preference("general.useragent.override", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            options.profile = profile
        
        # Remove Chrome-specific arguments that don't work with Firefox
        # (keeping only the essential one)
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        if BROWSER == "FIREFOX":
            logger.info(f"Basic stealth Firefox profile loaded from: {PROFILE_PATH}")
        
    except Exception as e:
        logger.error(f"Error setting up Firefox profile: {str(e)}")
        # Fallback configuration
        if BROWSER == "FIREFOX":
            profile = webdriver.FirefoxProfile()
            profile.set_preference("dom.webdriver.enabled", False)
            profile.set_preference("useAutomationExtension", False)
            options.profile = profile
    
    return options


def handle_cookie_consent(driver):
    """
    Handle cookie consent banners that may appear on job sites
    """
    try:
        # Common cookie consent button selectors
        cookie_selectors = [
            # Generic selectors
            '//button[contains(text(), "Accept")]',
            '//button[contains(text(), "Accept All")]',
            '//button[contains(text(), "Accept Cookies")]',
            '//button[contains(text(), "Allow All")]',
            '//button[contains(text(), "I Accept")]',
            '//button[contains(text(), "OK")]',
            '//button[contains(text(), "Got it")]',
            '//button[contains(text(), "Continue")]',
            
            # ID-based selectors
            '//button[@id="accept-cookies"]',
            '//button[@id="cookie-accept"]',
            '//button[@id="acceptCookies"]',
            '//button[@id="onetrust-accept-btn-handler"]',  # OneTrust
            '//button[@id="hs-eu-confirmation-button"]',     # HubSpot
            
            # Class-based selectors
            '//button[contains(@class, "accept")]',
            '//button[contains(@class, "cookie-accept")]',
            '//button[contains(@class, "consent-accept")]',
            '//button[contains(@class, "gdpr-accept")]',
            
            # Data attribute selectors
            '//button[@data-testid="accept-cookies"]',
            '//button[@data-cy="accept-cookies"]',
            '//button[@data-automation-id="cookie-accept"]',
            
            # Workday specific selectors
            '//button[contains(@class, "css-") and contains(text(), "Accept")]',
            '//div[@data-automation-id="cookieBanner"]//button[contains(text(), "Accept")]',
        ]
        
        # Try each selector
        for selector in cookie_selectors:
            try:
                cookie_buttons = driver.find_elements(By.XPATH, selector)
                if cookie_buttons:
                    # Click the first visible button
                    for button in cookie_buttons:
                        if button.is_displayed() and button.is_enabled():
                            driver.execute_script("arguments[0].click();", button)
                            logger.info(f"Clicked cookie consent button using selector: {selector}")
                            wait_here(1, 2)
                            return True
            except Exception as e:
                continue
        
        # Try CSS selectors as fallback
        css_selectors = [
            'button[id*="accept"]',
            'button[class*="accept"]',
            'button[data-testid*="accept"]',
            '.cookie-banner button',
            '.consent-banner button',
            '#cookie-consent button',
        ]
        
        for css_selector in css_selectors:
            try:
                cookie_buttons = driver.find_elements(By.CSS_SELECTOR, css_selector)
                if cookie_buttons:
                    for button in cookie_buttons:
                        if button.is_displayed() and button.is_enabled():
                            button_text = button.text.lower()
                            if any(word in button_text for word in ['accept', 'allow', 'ok', 'continue', 'got it']):
                                driver.execute_script("arguments[0].click();", button)
                                logger.info(f"Clicked cookie consent button using CSS selector: {css_selector}")
                                wait_here(1, 2)
                                return True
            except Exception as e:
                continue
                
        logger.info("No cookie consent banner found or already accepted")
        return False
        
    except Exception as e:
        logger.error(f"Error handling cookie consent: {str(e)}")
        return False


def apply_to_job(job_url):
    """
    Apply to a Job on Workday
    Returns: tuple (success: bool, error_message: str)
    """
    driver = None
    error_message = ""

    try:
        logger.info("---Loading Driver")
        if BROWSER == "FIREFOX":
            driver = webdriver.Firefox(options=make_options())
        else:
            driver = webdriver.Chrome(options=make_options())
        driver.maximize_window()
        logger.info("---Driver Loaded")

        # Loading the Job Base Page
        driver.get(job_url)
        logger.info(f"---Page Loaded - {job_url}")
        wait_here(3, 5)

        hide_webdriver(driver)

        # inject_stealth_scripts(driver)
        random_scroll(driver)
        wait_here(3, 5)

        # Handle cookie consent banner if present
        handle_cookie_consent(driver)
        wait_here(2, 3)

        # Checking if the user login is valid - otherwise trying to log into the account and then open job url
        account_settings_button = driver.find_elements(By.XPATH, '//button[@id="accountSettingsButton"]/span[2]')
        if account_settings_button:
            login_info = account_settings_button[0].text
            if login_info == os.getenv('USER_EMAIL'):
                logger.info(f"User {login_info} is logged in")
            else:
                error_message = f"User {os.getenv('USER_EMAIL')} is not logged in browser"
                logger.error(error_message)
                if driver:
                    driver.quit()
                    del driver
                return False, error_message
        else:
            logger.error(f"User {os.getenv('USER_EMAIL')} is not logged in browser")

            account_settings_button = driver.find_elements(By.XPATH, '//button[@data-automation-id="utilityButtonSignIn"]/span[2]')
            if account_settings_button:
                login_info = account_settings_button[0].text
            else:
                error_message = "Sign In button not found"
                logger.error(error_message)
                if driver:
                    driver.quit()
                    del driver
                return False, error_message

            if login_info.lower() == "sign in":
                pass
            else:
                error_message = "Sign In button not found"
                logger.error(error_message)
                if driver:
                    driver.quit()
                    del driver
                return False, error_message

            logger.info("Trying to Log in the user")
            account_settings_button = driver.find_elements(By.XPATH, '//button[@data-automation-id="utilityButtonSignIn"]')
            if account_settings_button:
                pass

            driver.execute_script("arguments[0].click();", account_settings_button[0])
            logger.info("Clicked on Account Settings button")
            wait_here(3, 5)
            # Replace manual clear/send_keys with safe_send_keys
            if not safe_send_keys(driver, '//input[contains(@id, "input") and @data-automation-id="email"]', os.getenv('USER_EMAIL')):
                error_message = "Email input field not found or failed to send keys"
                logger.error(error_message)
                if driver:
                    driver.quit()
                    del driver
                return False, error_message
            wait_here(3, 5)

            # Replace manual clear/send_keys with safe_send_keys
            if not safe_send_keys(driver, '//input[contains(@id, "input") and @data-automation-id="password"]', os.getenv('USER_PASSWORD')):
                error_message = "Password input field not found or failed to send keys"
                logger.error(error_message)
                if driver:
                    driver.quit()
                    del driver
                return False, error_message
            wait_here(3, 5)

            sign_in_button = driver.find_elements(By.XPATH, '//button[@type="submit" and @data-automation-id="signInSubmitButton"]/preceding-sibling::div')
            if sign_in_button:
                driver.execute_script("arguments[0].click();", sign_in_button[0])
                logger.info("Clicked on Sign In button")
            else:
                error_message = "Sign In button not found"
                logger.error(error_message)
                if driver:
                    driver.quit()
                    del driver
                return False, error_message
            wait_here(3, 5)

            unknown_account = driver.find_elements(By.XPATH, "//p[contains(text(), 'You may have entered the wrong email address or password or your account might be locked.')]")
            if unknown_account:
                error_message = "Unknown account error - wrong credentials or locked account"
                logger.error(error_message)
                logger.info("Making new account")

                wait_here(3, 5)

                make_new_account(driver)

            # Loading the Job Base Page
            driver.get(job_url)
            logger.info(f"---Page Loaded - {job_url}")
            wait_here(3, 5)

            # Check if login was successful
            account_settings_button = driver.find_elements(By.XPATH, '//button[@id="accountSettingsButton"]/span[2]')
            if account_settings_button:
                login_info = account_settings_button[0].text
                if login_info == os.getenv('USER_EMAIL'):
                    logger.info(f"User {login_info} is logged in")
                else:
                    error_message = f"User {os.getenv('USER_EMAIL')} is not logged in browser after login attempt"
                    logger.error(error_message)
                    if driver:
                        driver.quit()
                        del driver
                    return False, error_message
            else:
                signin_button = driver.find_elements(By.XPATH, '//button[@data-automation-id="utilityButtonSignIn"]')
                error_message = "Account Settings button not found after Account Creation"
                logger.error(error_message)
                if signin_button:
                    logger.info("Sign IN button is there --- trying without signing in")
                else:
                    if driver:
                        driver.quit()
                        del driver
                    return False, error_message

        wait_here(3, 5)

        skip_process_elements = False

        apply_manually_button = driver.find_elements(By.XPATH, '//a[@data-automation-id="applyManually"]')
        if apply_manually_button:
            link_to_follow = apply_manually_button[0].get_attribute('href')
            driver.get(link_to_follow)
            logger.info(f"Navigated to Apply Manually page - {link_to_follow}")
            wait_here(3, 5)
        else:
            page_loaded = wait_for_page_loading(driver)
            if not page_loaded:
                error_message = "Page stuck at loading"
                logger.error(error_message)
                if driver:
                    driver.quit()
                    del driver
                return False, error_message
            
            logger.error("Apply Manually button not found")
            wait_here(3, 5)

            driver.get(job_url)
            wait_here(3, 5)

            continue_button = driver.find_elements(By.XPATH, '//a[@data-automation-id="continueButton" or @data-automation-id="adventureButton"]')
            if continue_button:
                link_to_follow = continue_button[0].get_attribute('href')
                driver.get(link_to_follow)
                logger.info(f"Navigated to Continue page - {link_to_follow}")
                wait_here(5, 7)

                page_loaded = wait_for_page_loading(driver)
                if not page_loaded:
                    error_message = "Page stuck at loading"
                    logger.error(error_message)
                    if driver:
                        driver.quit()
                        del driver
                    return False, error_message

                apply_manually_button = driver.find_elements(By.XPATH, '//a[@data-automation-id="applyManually"]')
                if apply_manually_button:
                    link_to_follow = apply_manually_button[0].get_attribute('href')
                    driver.get(link_to_follow)
                    logger.info(f"Navigated to Apply Manually page - {link_to_follow}")
                    wait_here(3, 5)
                else:
                    error_message = "Apply Manually button not found after continue"
                    logger.error(error_message)
                    wait_here(3, 5)

                    apply_manually_button = driver.find_elements(By.XPATH, '//a[@data-automation-id="applyManually"]')
                    if apply_manually_button:
                        link_to_follow = apply_manually_button[0].get_attribute('href')
                        driver.get(link_to_follow)
                        logger.info(f"Navigated to Apply Manually page - {link_to_follow}")
                        wait_here(3, 5)
                    else:
                        error_message = "Apply Manually button not found after continue - 2"
                        logger.error(error_message)
                        wait_here(3, 5)


                page_loaded = wait_for_page_loading(driver)
                if not page_loaded:
                    error_message = "Page stuck at loading"
                    logger.error(error_message)
                    if driver:
                        driver.quit()
                        del driver
                    return False, error_message

                if driver.find_elements(By.XPATH, '//button[@data-automation-id="createAccountSubmitButton"]'):
                    make_new_account(driver, skip_create_link=True)

                page_loaded = wait_for_page_loading(driver)
                if not page_loaded:
                    error_message = "Page stuck at loading"
                    logger.error(error_message)
                    if driver:
                        driver.quit()
                        del driver
                    return False, error_message

            else:
                logger.error("Continue button not found")

                if driver.find_elements(By.XPATH, '//button[@data-automation-id="createAccountSubmitButton"]'):
                    make_new_account(driver, skip_create_link=True)

                page_loaded = wait_for_page_loading(driver)
                if not page_loaded:
                    error_message = "Page stuck at loading"
                    logger.error(error_message)
                    if driver:
                        driver.quit()
                        del driver
                    return False, error_message

                # if TESTING:
                #     skip_process_elements = True
                #     error_message = True
                # else:
                error_message = process_the_elements(driver, page=1)
                if error_message not in [True, False]:
                    if driver:
                        driver.quit()
                        del driver
                    return False, error_message

                if error_message:
                    skip_process_elements = True
                else:
                    error_message = "Failed to process elements on job page"
                    if driver:
                        driver.quit()
                        del driver
                    return False, error_message

        if driver.find_elements(By.XPATH, '//button[@data-automation-id="createAccountSubmitButton"]'):
            make_new_account(driver, skip_create_link=True)

        page_loaded = wait_for_page_loading(driver)
        if not page_loaded:
            error_message = "Page stuck at loading"
            logger.error(error_message)
            if driver:
                driver.quit()
                del driver
            return False, error_message

        # if TESTING:
        #     pass
        # else:
        if not skip_process_elements:
            error_message = process_the_elements(driver, page=1)
            if error_message not in [True, False]:
                if driver:
                    driver.quit()
                    del driver
                return False, error_message

        # input("Press any key to continue to Page 2...")
        is_success = press_next_button(driver)
        if not is_success:
            error_message = "Failed to proceed to next page - next button not found or not clickable"
            if driver:
                driver.quit()
                del driver
            return False, error_message

        process_data_insertion_page2(driver)

        # if TESTING:
        #     return True, "Page 2 completed successfully"

        # TODO: has new fields
        # https://pureinsurance.wd5.myworkdayjobs.com/en-US/PURE/job/Remote---US/Sr-Data-Scientist_R2430/apply/applyManually?source=LinkedIn
        # https://reliaquest.wd5.myworkdayjobs.com/en-US/ReliaQuest_Careers/job/Dublin/Data-Scientist_R14215/apply?source=LinkedIn

        while True:
            try:
                wait_here(1, 2)  # Small wait before getting element
                submit_button = driver.find_element(By.XPATH, '//button[@data-automation-id="pageFooterNextButton" and contains(text(), "Submit")]')
            except:
                submit_button = None
            
            if submit_button:
                # input("Press any key to submit the form ...")
                driver.execute_script("arguments[0].click();", submit_button)
                break

            is_success = press_next_button(driver)
            if not is_success:
                error_message = "Failed to proceed through application pages - next button not found"
                if driver:
                    driver.quit()
                    del driver
                return False, error_message

            process_the_elements(driver)

            if is_application_questions_page(driver):
                check_and_fill_application_questions(driver)

            elif is_disability_page(driver):
                check_and_fill_disability(driver)
                wait_here(3, 5)

            elif is_voluntry_disclosures_page(driver):
                check_and_fill_voluntry_disclosures(driver)
                wait_here(3, 5)

        input('Press any key to close browser...')

        # closing driver
        logger.info("---Closing the Automation Window")
        driver.quit()
        del driver
        logger.info("---Automation Window Closed")

        return True, ""

    except Exception as exc:
        error_message = f"Exception during job application: {str(exc)}"
        logger.error(error_message, exc_info=True)

        if TESTING:
            input("Testing system ---- waiting for user input")

        if driver:
            driver.quit()
            del driver
            driver = None

    return False, error_message


def make_new_account(driver, skip_create_link=False):
    """
    Make new account on workday
    """
    try:
        if not skip_create_link:
            create_account_link = driver.find_elements(By.XPATH, '//button[@data-automation-id="createAccountLink"]')
            driver.execute_script("arguments[0].click();", create_account_link[0])
            logger.info("Clicked on Create Account button")
            wait_here(2, 4)

        # Replace manual clear/send_keys with safe_send_keys
        if not safe_send_keys(driver, '//input[@data-automation-id="email"]', os.getenv('USER_EMAIL')):
            logger.error("Failed to enter email in account creation")
            return False
        
        wait_here(2, 4)
        # Replace manual clear/send_keys with safe_send_keys
        if not safe_send_keys(driver, '//input[@data-automation-id="password"]', os.getenv('USER_PASSWORD')):
            logger.error("Failed to enter password in account creation")
            return False
        
        wait_here(2, 4)
        # Replace manual clear/send_keys with safe_send_keys
        if not safe_send_keys(driver, '//input[@data-automation-id="verifyPassword"]', os.getenv('USER_PASSWORD')):
            logger.error("Failed to enter verify password in account creation")
            return False
        
        wait_here(1, 3)

        create_account_checkbox = driver.find_elements(By.XPATH, '//input[@data-automation-id="createAccountCheckbox"]')
        if create_account_checkbox:
            driver.execute_script("arguments[0].click();", create_account_checkbox[0])
            logger.info("Clicked on Create Account Checkbox")
            wait_here(3, 5)

        create_account_submit_button = driver.find_elements(By.XPATH, '//button[@data-automation-id="createAccountSubmitButton"]/preceding-sibling::div')
        create_account_submit_button[0].click()
        logger.info("Clicked on Create Account Submit Button")
        wait_here(3, 5)

        # input("Account created successfuly - Press any key to continue...")

    except Exception as exc:
        logger.error("Unable to create account on workday")
        logger.error(f"Exception: {exc}", exc_info=True)


def delete_experience_from_page2(driver):
    """
    Deletes work experience from Page 2
    """
    try:
        delete_work_experiences = driver.find_elements(By.XPATH, '//h4[contains(@id, "Work-Experience")]/following-sibling::button[contains(text(), "Delete")]')
        i = 1
        while i <= len(delete_work_experiences):
            driver.find_element(By.XPATH, "//h4[contains(@id, 'Work-Experience')]/following-sibling::button[contains(text(), 'Delete')]").click()
            i = i+1
            time.sleep(1)
    except Exception as exc:
        logger.error(f"Exception: {exc}", exc_info=True)


def delete_education_from_page2(driver):
    """
    Deletes education from Page 2
    """
    try:
        delete_work_experiences = driver.find_elements(By.XPATH, '//h4[contains(@id, "Education")]/following-sibling::button[contains(text(), "Delete")]')
        i = 1
        while i <= len(delete_work_experiences):
            driver.find_element(By.XPATH, '//h4[contains(@id, "Education")]/following-sibling::button[contains(text(), "Delete")]').click()
            i = i+1
            time.sleep(1)
    except Exception as exc:
        logger.error(f"Exception: {exc}", exc_info=True)


def escape_xpath_text(text):
    """
    Escapes text for use in an XPath expression.
    """
    if "'" in text and '"' in text:
        # Split by single quote and rejoin with the XPath literal for a single quote
        return "concat('" + "', \"'\", '".join(text.split("'")) + "')"
    elif "'" in text:
        # Contains only single quotes, so use double quotes to enclose it
        return f'"{text}"'
    else:
        # Contains no single quotes (or no quotes at all), so use single quotes
        return f"'{text}'"


def open_and_click_dropdown(driver, xpath_to_search, value_to_click, text_to_print):
    """
    Performs the clicks on Dropdowns
    """
    error = 'dropdown not found'
    xpath_to_use = ''
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", driver.find_element(By.XPATH, xpath_to_search))
        wait_here(2, 5)
        error = "element found - not clicked"
        driver.find_element(By.XPATH, xpath_to_search).click()
        wait_here(5, 10)
        error = "element clicked - dropdown value not found"
        if isinstance(value_to_click, list):
            xpath_to_use =  "//div["
            for index_, val_ in enumerate(value_to_click):
                xpath_to_use +=  f"contains(text(), '{val_}')"
                if index_ < (len(value_to_click)-1):
                    xpath_to_use += ' or '
            xpath_to_use += "]"

            ad = driver.find_elements(By.XPATH, xpath_to_use)
            for elem_ in ad:
                driver.execute_script("arguments[0].click();", elem_)
                wait_here(1, 2)
        else:
            xpath_to_use =  f"//div[contains(text(), {escape_xpath_text(value_to_click)})]"
            ad = driver.find_elements(By.XPATH, xpath_to_use)

            best_match = 0
            if len(ad) > 1:
                logger.info(f"Multiple elements found for {value_to_click} - {ad}")
                for ind_, ad_ in enumerate(ad):
                    if value_to_click in ad_.text:
                        if value_to_click == ad_.text:
                            best_match = ind_
                        # driver.execute_script("arguments[0].click();", ad_)
                        # wait_here(1, 2)
                        # break

            ad[best_match].click()
        wait_here(3, 5)
        return True
    except Exception as exc:
        logger.info(f"{text_to_print} - Status: {error} - {repr(exc)} - {xpath_to_use}")
    return False


def process_data_insertion_page2(driver):
    """
    Processes Data Insertion
    """
    is_success = True
    try:
        delete_experience_from_page2(driver)
        for work_experience_index, work_experience in enumerate(PROFILE_DATA['work_experiences']):
            logger.info(f"Work Experience {work_experience_index+1}")
            if work_experience_index == 0:
                try:
                    add_button = driver.find_element(By.XPATH, '//div[@aria-labelledby="Work-Experience-section"]//button[@data-automation-id="add-button" and contains(.//text(), "Add")]')
                    driver.execute_script("arguments[0].click();", add_button)
                except:
                    print("Exception: 'Add button not found'")
            else:
                add_another_button = driver.find_element(By.XPATH, '//div[@aria-labelledby="Work-Experience-section"]//button[@data-automation-id="add-button" and contains(.//text(), "Add Another")]')
                driver.execute_script("arguments[0].click();", add_another_button)
                time.sleep(2)

            time.sleep(2)
            work_experience_xpath = '//div[@aria-labelledby="Work-Experience-section"]//div[@aria-labelledby="Work-Experience-' + str(work_experience_index+1)+'-panel"]'
            work_experience_div = driver.find_element(By.XPATH, work_experience_xpath)
            work_experience.update({'div': work_experience_div, 'xpath': work_experience_xpath})
            fill_work_experience(driver, work_experience)
            time.sleep(2)
        
        # deleting empty work experience
        try:
            xpath_for_deletion = '//input[@name="jobTitle" and @value=""]/parent::div/parent::div/parent::div[@data-fkit-id]/parent::div[@data-fkit-id]/preceding-sibling::div[1]/h4[contains(@id, "Work-Experience")]/following-sibling::button[contains(text(), "Delete")]'
            delete_work_experiences = driver.find_elements(By.XPATH, xpath_for_deletion)
            if delete_work_experiences:
                # perform click using javascript
                driver.execute_script("arguments[0].click();", driver.find_element(By.XPATH, xpath_for_deletion))
                time.sleep(2)
        except Exception as exc:
            logger.error(f"Exception: {exc}", exc_info=True)

        resume_section = driver.find_element(By.XPATH, '//div[@aria-labelledby="Resume/CV-section"]')
        resume_section.location_once_scrolled_into_view
        time.sleep(2)

        delete_resumes = driver.find_elements(By.XPATH, '//div[@aria-labelledby="Resume/CV-section"]//button[@data-automation-id="delete-file"]')
        i = 1
        while i <= len(delete_resumes):
            driver.find_element(By.XPATH, '//div[@aria-labelledby="Resume/CV-section"]//button[@data-automation-id="delete-file"]').click()
            i = i+1
            time.sleep(1)

        delete_education_from_page2(driver)
        education_running_index = 0
        for education_index, education in enumerate(PROFILE_DATA['education_details']):
            logger.info(f"Education {education_index+1}")
            if education_index == 0:
                try:
                    add_button = driver.find_element(By.XPATH, '//div[@aria-labelledby="Education-section"]//button[@data-automation-id="add-button" and contains(.//text(), "Add")]')
                    driver.execute_script("arguments[0].click();", add_button)
                except:
                    print("Exception: 'Add button not found'")
            else:
                add_another_button = driver.find_element(By.XPATH, '//div[@aria-labelledby="Education-section"]//button[@data-automation-id="add-button" and contains(.//text(), "Add Another")]')
                driver.execute_script("arguments[0].click();", add_another_button)
                time.sleep(2)

            time.sleep(2)
            education_xpath = '//div[@aria-labelledby="Education-section"]//div[@aria-labelledby="Education-' + str(education_index+1)+'-panel"]'
            education_div = driver.find_element(By.XPATH, education_xpath)
            PROFILE_DATA['education_details'][education_running_index].update({'div': education_div, 'xpath': education_xpath})
            if fill_education(driver, PROFILE_DATA['education_details'][education_running_index]):
                education_running_index += 1
            time.sleep(2)

        file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file']")
        file_input.send_keys(PROFILE_DATA['resume_path'])
        time.sleep(10)

        try:
            linkedin_question = driver.find_element(By.CSS_SELECTOR, "input[type='text'][data-automation-id='linkedinQuestion']")
            linkedin_question.clear()
            linkedin_question.send_keys(PROFILE_DATA['linkedin_url'])
        except:
            print("Exception: 'No Linkedin input'")

        try:
            skills_field = '//div[@data-automation-id="formField-skills"]//input'
            skills_input = driver.find_elements(By.XPATH, skills_field)
            if skills_input:
                driver.execute_script("arguments[0].click();", skills_input[0])
                for skill in PROFILE_DATA['skills']:
                    skills_input[0].send_keys(skill)
                    skills_input[0].send_keys(Keys.ENTER)
                    wait_here(1, 2)
                    leaf_node = driver.find_elements(By.XPATH, '//div[@data-automation-id="promptLeafNode"]')
                    if leaf_node:
                        direct_click = driver.find_element(By.XPATH, '//div[@data-automation-id="promptLeafNode"]')
                        if direct_click:
                            driver.execute_script("arguments[0].click();", direct_click)
        except Exception as exc:
            logger.error(f"Exception while adding skills: {exc}", exc_info=True)

        # TODO: Handle language -> https://generalmotors.wd5.myworkdayjobs.com/en-US/Careers_GM/job/Austin%2C-Texas%2C-United-States-of-America/Data-Scientist_JR-202500570/apply?source=LinkedIn
        try:
            if open_and_click_dropdown(driver, xpath_to_search='//button[@name="language"]', value_to_click='English', text_to_print='Language not found'):
                wait_here(3, 5)

            driver.find_element(By.XPATH, '//input[contains(@id, "language") and contains(@id, "native")]').click()

            if open_and_click_dropdown(driver, xpath_to_search='//button[@aria-label="Conversational/Spoken Word Select One Required"]', value_to_click=['Advanced', 'Fluent'], text_to_print='Conversational/Spoken not found'):
                wait_here(3, 5)

            if open_and_click_dropdown(driver, xpath_to_search='//button[@aria-label="Overall Select One Required"]', value_to_click=['Advanced', 'Fluent'], text_to_print='Overall not found'):
                wait_here(3, 5)

            if open_and_click_dropdown(driver, xpath_to_search='//button[@aria-label="Written Communication Select One Required"]', value_to_click=['Advanced', 'Fluent'], text_to_print='Written Communication not found'):
                wait_here(3, 5)

        except Exception as exc:
            logger.error(f"Failed while adding language: {exc}", exc_info=True)

        # deleting empty education
        try:
            wait_here(2, 4)
            xpath_for_deletion = '//h4[contains(@id, "Education") and ./parent::div/following-sibling::div//input[contains(@id, "education") and contains(@id, "school") and (@value="" or not(@value))] and not(./parent::div/following-sibling::div//li[@data-automation-id="menuItem"])]/following-sibling::button[contains(.//text(), "Delete")]'
            delete_education = driver.find_elements(By.XPATH, xpath_for_deletion)
            if delete_education:
                del_ind = 0
                while True:
                    driver.execute_script("arguments[0].click();", driver.find_element(By.XPATH, xpath_for_deletion))
                    print(f"----Deleted Education {del_ind+1}")
                    wait_here(2, 4)
                    del_ind += 1
                time.sleep(2)
        except Exception as exc:
            logger.error(f"Exception: {exc}", exc_info=True)

    except Exception as exc:
        logger.error(f"Exception in pressing next button: {exc}", exc_info=True)
        is_success = False

    return is_success


def fill_work_experience(driver, work_experience):
    """
    Fills in the work experience using hybrid approach
    """
    # Use hybrid approach for all fields
    safe_send_keys(work_experience['div'], './/input[@name="jobTitle"]', work_experience['job_title'])
    safe_send_keys(work_experience['div'], './/input[@name="companyName"]', work_experience['company'])
    
    wait_here(2, 4)
    safe_send_keys(work_experience['div'], './/input[@name="location"]', work_experience['location'])
    
    wait_here(2, 4)
    safe_send_keys(work_experience['div'], './/textarea[contains(@id, "roleDescription")]', work_experience['role_description'])

    change_value_of_date(driver, f'{work_experience["xpath"]}//input[contains(@id, "startDate-dateSectionMonth")]', 0, work_experience['start_month'])
    change_value_of_date(driver, f'{work_experience["xpath"]}//input[contains(@id, "startDate-dateSectionYear")]', 2025, work_experience['start_year'])

    change_value_of_date(driver, f'{work_experience["xpath"]}//input[contains(@id, "endDate-dateSectionMonth")]', 0, work_experience['end_month'])
    change_value_of_date(driver, f'{work_experience["xpath"]}//input[contains(@id, "endDate-dateSectionYear")]', 2025, work_experience['end_year'])

    return

def add_value_to_search_field(driver, xpath_to_use, value_to_add):
    """
    Adds value to a search field - particularly in education
    """
    try:
        search_field = driver.find_element(By.XPATH, xpath_to_use)
        driver.execute_script("arguments[0].click();", search_field)
        search_field.clear()
        search_field.send_keys(value_to_add)
        search_field.send_keys(Keys.ENTER)
        wait_here(1, 2)
        leaf_node = driver.find_elements(By.XPATH, '//div[@data-automation-id="promptLeafNode" and not(contains(./div/text(), "No Items."))]')
        if leaf_node:
            driver.execute_script("arguments[0].click();", leaf_node[0])
            return True
        search_field = driver.find_element(By.XPATH, xpath_to_use)
        search_field.clear()
    except Exception as exc:
        logger.error(f"Exception while adding value to search field: {exc}", exc_info=True)

    return False


def fill_education(driver, education):
    """
    Fills in the education using hybrid approach
    """
    # Use hybrid approach for all fields
    if driver.find_elements(By.XPATH, f'{education["xpath"]}//input[@name="schoolName"]'):
        safe_send_keys(education['div'], './/input[@name="schoolName"]', education['institution'])
    else:
        # f'{education["xpath"]}//div[@data-automation-id="formField-school"]//input'
        if not add_value_to_search_field(driver, f'{education["xpath"]}//div[@data-automation-id="formField-school"]//input', education['institution']):
            return False

    # TODO: Handle university name -> https://generalmotors.wd5.myworkdayjobs.com/en-US/Careers_GM/job/Austin%2C-Texas%2C-United-States-of-America/Data-Scientist_JR-202500570/apply?source=LinkedIn
    # https://reliaquest.wd5.myworkdayjobs.com/en-US/ReliaQuest_Careers/job/Dublin/Data-Scientist_R14215/apply?source=LinkedIn

    if open_and_click_dropdown(driver, xpath_to_search=f'{education["xpath"]}//button[@name="degree"]', value_to_click=education["type"], text_to_print='Education Type not found'):
        wait_here(3, 5)

    # change_value_of_date(driver, f'{education["xpath"]}//input[contains(@id, "firstYearAttended-dateSectionYear")]', 2025, education['year'])
    change_value_of_date(driver, f'{education["xpath"]}//input[contains(@id, "lastYearAttended-dateSectionYear")]', 2025, education['year'])

    return True


def change_value_of_date(driver, xpath_to_use, default_value, value_to_set):
    try:
        driver.execute_script("arguments[0].click();", driver.find_element(By.XPATH, f'{xpath_to_use}/preceding-sibling::div'))
        md_ = driver.find_element(By.XPATH, f'{xpath_to_use}')
        # md_.send_keys(Keys.DELETE)
        time.sleep(0.2)
        if default_value != 0:
            md_.send_keys(Keys.UP)
            time.sleep(0.1)

        if value_to_set > default_value:
            for i in range(default_value, (value_to_set-default_value)):
                md_.send_keys(Keys.UP)
                time.sleep(0.1)
        else:
            for i in range(default_value, value_to_set, -1):
                md_.send_keys(Keys.DOWN)
                time.sleep(0.1)
    except Exception as exc:
        logger.error(f"Unable to change value of date ----- Exception: {exc}")


def press_next_button(driver):
    """
    Presses Next Button (if available)
    """
    is_success = True
    try:
        print("Moving to next page....")
        try:
            wait_here(1, 2)  # Small wait before getting element
            button = driver.find_element(By.XPATH, '//button[@data-automation-id="pageFooterNextButton"]')
            driver.execute_script("arguments[0].click();", button)
        except:
            logger.error(" ----- Unable to click next button -----")
            return is_success

        wait_here(2, 4)

        try:
            error_button = driver.find_elements(By.XPATH, "//h3[contains(./button/div/text(), 'Errors Found')]")
            if error_button:
                logger.error(" ----- Unable to fill all fields -----")
                is_success = False

                if TESTING:
                    input("----------- Error Encountered - Press any key to continue........")
        except Exception as exc:
            logger.info(f"No Errors Found - {repr(exc)}")

        wait_here(10, 15)
    except Exception as exc:
        logger.error(f"Exception in pressing next button: {exc}", exc_info=True)
        is_success = False
        if TESTING:
            input("----------- Error Encountered - Press any key to continue........")

    return is_success


def process_the_elements(driver, page=None):
    """
    Process the elements on the page
    """
    # global LLM_APPLIER

    if page == 1:
        try:
            WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.XPATH, '//div[@role="group"]')))
        except Exception as exc:
            logger.error(f"Exception in process_the_elements: {exc}")
            return "Either applied already or job not availabe now"

        wait_here(3, 5)

        try:
            if driver.find_elements(By.XPATH, '//div[@data-automation-id="formField-source"]//button'):
                if open_and_click_dropdown(driver, xpath_to_search='//div[@data-automation-id="formField-source"]//button', value_to_click='LinkedIn', text_to_print='Where did you hear -- not found'):
                    wait_here(3, 5)

            driver.find_element(By.XPATH, '//div[@data-automation-id="formField-source"]//input').click()
            wait_here(2, 4)
            if driver.find_elements(By.XPATH, '//div[@data-automation-id="promptLeafNode"]'):
                while True:
                    direct_click = driver.find_element(By.XPATH, '//div[@data-automation-id="promptLeafNode"]')
                    if direct_click:
                        driver.execute_script("arguments[0].click();", direct_click)
                        wait_here(2, 4)
                    else:
                        break

            safe_send_keys(driver, '//div[@data-automation-id="formField-source"]//input', 'LinkedIn')
            wait_here(1, 1)
            driver.find_element(By.XPATH, '//div[@data-automation-id="formField-source"]//input').send_keys(Keys.ENTER)
            wait_here(2, 4)

        except Exception as exc:
            logger.error(f"Where did you hear? - Not found - {repr(exc)}", exc_info=True)

        if open_and_click_dropdown(driver, xpath_to_search="//button[@id='country--country']", value_to_click=PROFILE_DATA["country"], text_to_print="Country not found"):
            wait_here(3, 5)

        try:
            elem_to_click = driver.find_element(By.XPATH, '//div[@data-automation-id="formField-candidateIsPreviousWorker"]//input[@value="false"]')
            elem_to_click.click()
        except Exception as exc:
            print("Exception: 'No previousWorker--candidateIsPreviousWorker' found - ", repr(exc))

        try:
            safe_send_keys(driver, '//div[@data-automation-id="formField-legalName--firstName"]//input', PROFILE_DATA["first_name"])
        except Exception as exc:
            print("Exception: 'name--legalName--firstName' not found - ", repr(exc))

        try:
            safe_send_keys(driver, '//div[@data-automation-id="formField-legalName--lastName"]//input', PROFILE_DATA["last_name"])
        except Exception as exc:
            print("Exception: 'LastName' not found - ", repr(exc))
        
        try:
            safe_send_keys(driver, '//input[@id="address--addressLine1"]', PROFILE_DATA["address_line_1"])
        except Exception as exc:
            print("Exception: 'address--addressLine1' not found - ", repr(exc))

        try:
            safe_send_keys(driver, '//div[@data-automation-id="formField-city"]//input', PROFILE_DATA["address_city"])
        except Exception as exc:
            print("Exception: 'address--city' not found - ", repr(exc))

        if open_and_click_dropdown(driver, xpath_to_search="//div[@data-automation-id='formField-countryRegion']//button", value_to_click=PROFILE_DATA["address_state"], text_to_print="State not found"):
            wait_here(3, 5)

        try:
            safe_send_keys(driver, '//input[@id="address--postalCode"]', PROFILE_DATA["address_postal_code"])
        except Exception as exc:
            print("Exception: 'address--postalCode' not found - ", repr(exc))

        if open_and_click_dropdown(driver, xpath_to_search='//div[@data-automation-id="formField-phoneType"]//button', value_to_click='Mobile', text_to_print="Mobile Type not found"):
            wait_here(3, 5)

        try:
            safe_send_keys(driver, '//input[@id="phoneNumber--countryPhoneCode"]', PROFILE_DATA["phone_country_code"])
            driver.find_element(By.XPATH, '//input[@id="phoneNumber--countryPhoneCode"]').send_keys(Keys.ENTER)
        except Exception as exc:
            print("Exception: 'phoneNumber--countryPhoneCode' not found - ", repr(exc))

        try:
            safe_send_keys(driver, '//input[@id="phoneNumber--phoneNumber"]', PROFILE_DATA["phone_number"])
        except Exception as exc:
            print("Exception: 'phoneNumber--phoneNumber' not found - ", repr(exc))

        try:
            safe_send_keys(driver, '//div[@data-automation-id="formField-emailAddress"]//input', PROFILE_DATA["email"])
        except Exception as exc:
            print("Exception: 'emailAddress--emailAddress' not found - ", repr(exc))

        wait_here(3, 5)

        return True

    return False


def read_jobs_from_excel_with_status(file_path='jobs.xlsx'):
    """
    Read job URLs from Excel file and return DataFrame with status tracking
    
    Args:
        file_path (str): Path to the Excel file containing job URLs
        
    Returns:
        pandas.DataFrame: DataFrame with job URLs and status columns
    """
    try:
        # Read the Excel file
        df = pd.read_excel(file_path)

        # Log the column names to understand the structure
        logger.info(f"Excel file columns: {df.columns.tolist()}")

        # Try to find URL column (common names)
        url_column = None
        possible_url_columns = ['url', 'URL', 'job_url', 'Job URL', 'link', 'Link', 'job_link', 'Job Link']

        for col in possible_url_columns:
            if col in df.columns:
                url_column = col
                break

        if url_column is None:
            # If no standard column name found, use the first column
            url_column = df.columns[0]
            logger.warning(f"No standard URL column found. Using first column: {url_column}")

        # Add status columns if they don't exist
        if 'application_status' not in df.columns:
            df['application_status'] = 'pending'
        if 'error_message' not in df.columns:
            df['error_message'] = ''
        if 'applied_date' not in df.columns:
            df['applied_date'] = ''

        # Filter out rows with invalid URLs
        df = df[df[url_column].notna()]
        df = df[df[url_column].astype(str).str.strip() != '']
        df = df[df[url_column].astype(str).str.lower() != 'nan']
        df = df[df[url_column].astype(str).str.contains('http|www', case=False, na=False)]

        logger.info(f"Found {len(df)} valid job entries in Excel file")
        return df, url_column

    except FileNotFoundError:
        logger.error(f"Excel file not found: {file_path}")
        return pd.DataFrame(), None
    except Exception as exc:
        logger.error(f"Error reading Excel file: {exc}", exc_info=True)
        return pd.DataFrame(), None


def read_jobs_from_csv_with_status(file_path='jobs.csv'):
    """
    Read job URLs from CSV file and return DataFrame with status tracking
    
    Args:
        file_path (str): Path to the CSV file containing job URLs
        
    Returns:
        pandas.DataFrame: DataFrame with job URLs and status columns
    """
    try:
        # Read the CSV file
        df = pd.read_csv(file_path)

        # Log the column names to understand the structure
        logger.info(f"CSV file columns: {df.columns.tolist()}")

        # Try to find URL column (common names)
        url_column = None
        possible_url_columns = ['url', 'URL', 'job_url', 'Job URL', 'link', 'Link', 'job_link', 'Job Link']

        for col in possible_url_columns:
            if col in df.columns:
                url_column = col
                break

        if url_column is None:
            # If no standard column name found, use the first column
            url_column = df.columns[0]
            logger.warning(f"No standard URL column found. Using first column: {url_column}")

        # Add status columns if they don't exist
        if 'application_status' not in df.columns:
            df['application_status'] = 'pending'
        else:
            # Fill missing/empty application_status values with 'pending'
            df['application_status'] = df['application_status'].fillna('pending')
            df.loc[df['application_status'].astype(str).str.strip() == '', 'application_status'] = 'pending'
            
        if 'error_message' not in df.columns:
            df['error_message'] = ''
        if 'applied_date' not in df.columns:
            df['applied_date'] = ''

        # Filter out rows with invalid URLs
        df = df[df[url_column].notna()]
        df = df[df[url_column].astype(str).str.strip() != '']
        df = df[df[url_column].astype(str).str.lower() != 'nan']
        df = df[df[url_column].astype(str).str.contains('http|www', case=False, na=False)]

        logger.info(f"Found {len(df)} valid job entries in CSV file")
        return df, url_column

    except FileNotFoundError:
        logger.error(f"CSV file not found: {file_path}")
        return pd.DataFrame(), None
    except Exception as exc:
        logger.error(f"Error reading CSV file: {exc}", exc_info=True)
        return pd.DataFrame(), None


def update_job_status(file_path, job_url, status, error_message=''):
    """
    Update the status of a job application in the Excel or CSV file
    
    Args:
        file_path (str): Path to the Excel or CSV file
        job_url (str): The job URL to update
        status (str): Status - 'applied', 'failed', or 'error'
        error_message (str): Error message if status is 'error' or 'failed'
    """
    try:
        # Determine file type and read accordingly
        if file_path.endswith('.csv'):
            df, url_column = read_jobs_from_csv_with_status(file_path)
            file_type = 'csv'
        else:
            df, url_column = read_jobs_from_excel_with_status(file_path)
            file_type = 'excel'
            
        if df.empty or url_column is None:
            logger.error(f"Could not read {file_type.upper()} file for status update")
            return False

        # Find the row with matching URL
        mask = df[url_column] == job_url
        if not mask.any():
            logger.warning(f"Job URL not found in {file_type.upper()} file: {job_url}")
            return False

        # Update the status
        df.loc[mask, 'application_status'] = status
        df.loc[mask, 'error_message'] = error_message
        df.loc[mask, 'applied_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Save back to file
        if file_type == 'csv':
            df.to_csv(file_path, index=False)
        else:
            df.to_excel(file_path, index=False)
            
        logger.info(f"Updated job status: {job_url} -> {status}")
        return True

    except Exception as exc:
        logger.error(f"Error updating job status: {exc}", exc_info=True)
        return False


def read_jobs_from_excel(file_path='jobs.xlsx'):
    """
    Read job URLs from Excel file, excluding already applied jobs
    
    Args:
        file_path (str): Path to the Excel file containing job URLs
        
    Returns:
        list: List of job URLs that haven't been applied to yet
    """
    try:
        df, url_column = read_jobs_from_excel_with_status(file_path)
        if df.empty or url_column is None:
            return []

        # Filter out jobs that have already been applied to successfully
        pending_jobs = df[df['application_status'] == 'pending']
        
        # Extract URLs
        valid_urls = pending_jobs[url_column].tolist()
        
        logger.info(f"Found {len(valid_urls)} pending job applications (out of {len(df)} total jobs)")
        return valid_urls

    except Exception as exc:
        logger.error(f"Error reading Excel file: {exc}", exc_info=True)
        return []


def read_jobs_from_csv(file_path='jobs.csv'):
    """
    Read job URLs from CSV file, excluding already applied jobs
    
    Args:
        file_path (str): Path to the CSV file containing job URLs
        
    Returns:
        list: List of job URLs that haven't been applied to yet
    """
    try:
        df, url_column = read_jobs_from_csv_with_status(file_path)
        if df.empty or url_column is None:
            return []

        # Filter out jobs that have already been applied to successfully
        pending_jobs = df[df['application_status'] == 'pending']
        
        # Extract URLs
        valid_urls = pending_jobs[url_column].tolist()
        
        logger.info(f"Found {len(valid_urls)} pending job applications (out of {len(df)} total jobs)")
        return valid_urls

    except Exception as exc:
        logger.error(f"Error reading CSV file: {exc}", exc_info=True)
        return []


def process_all_jobs(file_path='jobs.csv'):
    """
    Process all jobs from the CSV or Excel file with status tracking
    
    Args:
        file_path (str): Path to the CSV or Excel file containing job URLs
    """
    logger.info("=== Starting Job Application Process ===")

    # Read job URLs from file (only pending ones)
    if file_path.endswith('.csv'):
        job_urls = read_jobs_from_csv(file_path)
        file_type = 'CSV'
    else:
        job_urls = read_jobs_from_excel(file_path)
        file_type = 'Excel'

    if not job_urls:
        logger.error(f"No pending job URLs found in {file_type} file. Exiting.")
        return

    logger.info(f"Processing {len(job_urls)} pending job applications")

    successful_applications = 0
    failed_applications = 0
    error_applications = 0

    for i, job_url in enumerate(job_urls):
        try:
            logger.info(f"\n=== Processing Job {i+1}/{len(job_urls)} ===")
            logger.info(f"Job URL: {job_url}")

            # Apply to the job -> calling main function
            success, error_message = apply_to_job(job_url)

            if success:
                successful_applications += 1
                logger.info(f"✅ Successfully processed job {i+1}")
                # Update file with success status
                update_job_status(file_path, job_url, 'applied')
            else:
                if error_message:
                    error_applications += 1
                    logger.error(f"❌ Error processing job {i+1}: {error_message}")
                    # Update file with error status
                    update_job_status(file_path, job_url, 'error', error_message)
                else:
                    failed_applications += 1
                    logger.error(f"❌ Failed to process job {i+1}")
                    # Update file with failed status
                    update_job_status(file_path, job_url, 'failed', 'Application failed without specific error')

            # Add a delay between applications to avoid being detected
            if i < len(job_urls) - 1:  # Don't wait after the last job
                wait_here(5, 10)  # Wait 5-10 seconds between applications

            if TESTING:
                input("Press any button to go to next job...")

        except Exception as exc:
            error_applications += 1
            error_msg = f"Exception processing job {i+1}: {str(exc)}"
            logger.error(error_msg, exc_info=True)
            # Update file with error status
            update_job_status(file_path, job_url, 'error', error_msg)
            # Continue with next job even if current one fails
            continue

    # Summary
    logger.info("\n=== Job Application Summary ===")
    logger.info(f"Total jobs processed: {len(job_urls)}")
    logger.info(f"Successful applications: {successful_applications}")
    logger.info(f"Failed applications: {failed_applications}")
    logger.info(f"Error applications: {error_applications}")
    if len(job_urls) > 0:
        logger.info(f"Success rate: {(successful_applications/len(job_urls)*100):.1f}%")


def inject_stealth_scripts(driver):
    """
    Inject JavaScript to hide automation traces
    """
    stealth_js = """
    // Remove webdriver property
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });
    
    // Mock plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });
    
    // Mock languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });
    
    // Mock permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
    
    // Hide automation in chrome object
    if (window.chrome) {
        Object.defineProperty(window.chrome, 'runtime', {
            get: () => ({
                onConnect: undefined,
                onMessage: undefined,
            }),
        });
    }
    
    // Mock screen properties
    Object.defineProperty(window.screen, 'colorDepth', {
        get: () => 24,
    });
    
    // Remove automation indicators
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    """
    
    try:
        driver.execute_script(stealth_js)
        logger.info("Stealth scripts injected successfully")
    except Exception as e:
        logger.warning(f"Could not inject stealth scripts: {str(e)}")


import random
from selenium.webdriver.common.action_chains import ActionChains

def human_like_click(driver, element):
    """
    Perform human-like click with random delays and movements
    """
    try:
        # Random delay before action
        time.sleep(random.uniform(0.5, 1.5))
        
        # Move to element with slight randomness
        actions = ActionChains(driver)
        actions.move_to_element_with_offset(element, 
            random.randint(-5, 5), random.randint(-5, 5))
        actions.pause(random.uniform(0.1, 0.3))
        actions.click()
        actions.perform()
        
        # Random delay after action
        time.sleep(random.uniform(0.3, 0.8))
        
    except Exception as e:
        # Fallback to regular click
        driver.execute_script("arguments[0].click();", element)

def human_like_type(element, text):
    """
    Type text with human-like delays
    """
    element.clear()
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.15))
    
    # Random pause after typing
    time.sleep(random.uniform(0.5, 1.0))

def random_scroll(driver):
    """
    Perform random scrolling to mimic human behavior
    """
    scroll_amount = random.randint(100, 500)
    direction = random.choice([1, -1])
    driver.execute_script(f"window.scrollBy(0, {scroll_amount * direction});")
    time.sleep(random.uniform(0.5, 1.5))


def hide_webdriver(driver):
    """
    Simple script to hide webdriver property
    """
    try:
        driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
        """)
        logger.info("WebDriver property hidden")
    except Exception as e:
        logger.warning(f"Could not hide webdriver: {str(e)}")


def is_disability_page(driver):
    """
    Checks if the current page is the disability page.
    """
    try:
        disability_field = driver.find_elements(By.XPATH, '//input[@id="selfIdentifiedDisabilityData--name"]')
        return bool(disability_field)
    except Exception as e:
        logger.warning(f"Could not check disability page: {str(e)}")
        return False


def is_voluntry_disclosures_page(driver):
    """
    Checks if the current page is the application questions page.
    """
    try:
        application_questions_field = driver.find_elements(By.XPATH, '//h2[contains(text(), "Voluntary Disclosures")]')
        return bool(application_questions_field)
    except Exception as e:
        logger.warning(f"Could not check application questions page: {str(e)}")
        return False


def is_application_questions_page(driver):
    """
    Checks if the current page is the application questions page.
    """
    try:
        application_questions_field = driver.find_elements(By.XPATH, '//h2[contains(text(), "Application Questions")]')
        return bool(application_questions_field)
    except Exception as e:
        logger.warning(f"Could not check application questions page: {str(e)}")
        return False


def check_and_fill_application_questions(driver):
    """
    Checks and fills the application questions
    """
    try:
        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "Have you previously been employed by our company?")]/following-sibling::div//button', value_to_click='No', text_to_print='Not Found - Have you been previously employed'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "relocation")]/following-sibling::div//button', value_to_click='Yes', text_to_print='Not Found - Relocation'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "Are you willing to work onsite?")]/following-sibling::div//button', value_to_click='No', text_to_print='Not Found - Are you willing to work onsite'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "authorization to work in") and not(contains(.//text(), "sponsorship"))]/following-sibling::div//button', value_to_click='Yes', text_to_print='Not Found - Authorization to work in'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "18 years")]/following-sibling::div//button', value_to_click='Yes', text_to_print='Not Found - 18 years'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "relative employed")]/following-sibling::div//button', value_to_click='No', text_to_print='Not Found - Relative Employed'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "government")]/following-sibling::div//button', value_to_click='No', text_to_print='Not Found - Government Related Question'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "nondisclosure clause")]/following-sibling::div//button', value_to_click='No', text_to_print='Not Found - Nondisclosure Clause'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "Artificial intelligence")]/following-sibling::div//button', value_to_click='Yes', text_to_print='Not Found - Artificial Intelligence Consent'):
            wait_here(3, 5)

        # if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "Are you eligible to work in the country you are applying?")]/following-sibling::div//button', value_to_click='Yes', text_to_print='Not Found - Are you eligible to work in the country you are applying?'):
        #     wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "eligible to work in the") and not(contains(.//text(), "sponsorship"))]/following-sibling::div//button', value_to_click='Yes', text_to_print='Not Found - Are you eligible to work in the country you are applying?'):
            wait_here(3, 5)
        
        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "annual salary")]/following-sibling::div//button', value_to_click='$150,000-$180,000', text_to_print='Not Found - Annual Salary'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "agree to communications")]/following-sibling::div//button', value_to_click='Yes', text_to_print='Not Found - Agree to Communication?'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "Do you have any commitments or agreements with other employers")]/following-sibling::div//button', value_to_click='No', text_to_print='Not Found - Do you have any commitments or agreements with other employers?'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "sponsorship")]/following-sibling::div//button', value_to_click='No', text_to_print='Not Found - Sponsership?'):
            wait_here(3, 5)

        # get date of first of next month
        # use datetime in below
        next_month = datetime.now().month + 1
        next_month_day = (datetime.now() + timedelta(days=30)).day
        next_month_year = (datetime.now() + timedelta(days=30)).year

        change_value_of_date(driver, '//legend[contains(.//text(), "What is your desired start date?") or contains(.//text(), "When are you available to begin?")]/following-sibling::div//input[contains(@id, "dateSectionMonth")]', 0, next_month)
        change_value_of_date(driver, '//legend[contains(.//text(), "What is your desired start date?") or contains(.//text(), "When are you available to begin?")]/following-sibling::div//input[contains(@id, "dateSectionDay")]', 0, next_month_day)
        change_value_of_date(driver, '//legend[contains(.//text(), "What is your desired start date?") or contains(.//text(), "When are you available to begin?")]/following-sibling::div//input[contains(@id, "dateSectionYear")]', 2025, next_month_year)
        wait_here(3, 5)

        # if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "Are you legally authorized to work in USA?")]/following-sibling::div//button', value_to_click='Yes', text_to_print='Not Found - Are you legally authorized to work in USA'):
            # wait_here(3, 5)
        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "Are you legally authorized to work")]/following-sibling::div//button', value_to_click='Yes', text_to_print='Not Found - Are you legally authorized to work in USA'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "Do you now, or will you in the future, need sponsorship from an employer in order to obtain, extend or renew your authorization to work in the United States (this includes H-1B, TN, O-1, F-1, etc.)?")]/following-sibling::div//button', value_to_click='No', text_to_print='Not Found - Do you now, or will you in the future, need sponsorship from an employer in order to obtain, extend or renew your authorization to work in the United States (this includes H-1B, TN, O-1, F-1, etc.)?'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "Can you travel as required for this position? (if applicable)")]/following-sibling::div//button', value_to_click='Yes', text_to_print='Not Found - Can you travel as required for this position? (if applicable)'):
            wait_here(3, 5)

        if open_and_click_dropdown(driver, xpath_to_search='//legend[contains(.//text(), "Are you willing to relocate for this position? (if applicable)")]/following-sibling::div//button', value_to_click='Yes', text_to_print='Not Found - Are you willing to relocate for this position? (if applicable)'):
            wait_here(3, 5)
    
    except Exception as e:
        logger.warning(f"Could not fill application questions field: {str(e)}")

def check_and_fill_disability(driver):
    """
    Checks if the disability field is present on the page and fills it if it is.
    """
    try:
        # Replace manual clear/send_keys with safe_send_keys
        safe_send_keys(driver, '//input[@id="selfIdentifiedDisabilityData--name"]', PROFILE_DATA['complete_name'])
        logger.info("Disability Name Field filled with name")
        
        wait_here(2, 4)
        # Replace manual clear/send_keys with safe_send_keys

        month = datetime.now().month
        day = (datetime.now()).day
        year = (datetime.now()).year

        change_value_of_date(driver, '//input[@id="selfIdentifiedDisabilityData--dateSignedOn-dateSectionMonth-input"]', 0, month)
        change_value_of_date(driver, '//input[@id="selfIdentifiedDisabilityData--dateSignedOn-dateSectionDay-input"]', 0, day)
        change_value_of_date(driver, '//input[@id="selfIdentifiedDisabilityData--dateSignedOn-dateSectionYear-input"]', 2025, year)
        wait_here(1, 2)
        try:
            driver.find_element(By.XPATH, '//input[@id="selfIdentifiedDisabilityData--name"]').click()
        except:
            pass
        wait_here(3, 5)

        no_disability_field = driver.find_elements(By.XPATH, '//div[contains(./label/text(), "No, I do not have a disability and have not had one in the past")]/div/input')
        if no_disability_field:
            driver.execute_script("arguments[0].click();", no_disability_field[0])
            logger.info("Disability No Field filled with no")

    except Exception as e:
        logger.warning(f"Could not fill disability field: {str(e)}")


def check_and_fill_voluntry_disclosures(driver):
    """
    Check and Fill Voluntry Disclosure
    """
    try:
        if open_and_click_dropdown(driver, xpath_to_search='//button[@id="personalInfoUS--veteranStatus"]', value_to_click=['I am not a veteran', 'I AM NOT A VETERAN'], text_to_print='Not Found - I am not a veteran'):
            wait_here(3, 5)

        try:
            asian_field = driver.find_element(By.XPATH, '//label[contains(text(), "Asian")]/preceding-sibling::div//input')
            driver.execute_script("arguments[0].click();", asian_field)
        except Exception as e:
            print(f"Asian field not found - {repr(e)}")

        if open_and_click_dropdown(driver, xpath_to_search='//button[@id="personalInfoUS--gender"]', value_to_click=['Male'], text_to_print='Not Found - I am not a veteran'):
            wait_here(3, 5)

        # personalInfoUS--ethnicity
        if open_and_click_dropdown(driver, xpath_to_search='//button[@id="personalInfoUS--ethnicity"]', value_to_click=['Asian'], text_to_print='Not Found - Ethnicity'):
            wait_here(3, 5)

        accept_terms_and_agreements = driver.find_element(By.XPATH, '//input[@id="termsAndConditions--acceptTermsAndAgreements"]')
        driver.execute_script("arguments[0].click();", accept_terms_and_agreements)
    except Exception as e:
        logger.warning(f"Could not fill disability field: {str(e)}")

    return


if __name__ == '__main__':
    # Process all jobs from the CSV file
    process_all_jobs('jobs.csv')
