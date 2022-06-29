"""
This module is intended to be used as a wrapper for Okta API calls that allows for rapid development of multi-threaded scripts using the Okta API.

:class OktaAPIBase: Base class that can be used to perform common Okta API patterns in a multi-threaded way and a wrapper for Okta API calls that also handles rate limiting.
:class OktaAPIError: An error type for errors thrown by the Okta API. Takes in information about the request and formats error messages to make troubleshooting the errors easy.

:raises AuthenticationError: This error is raised when the Okta API key is invalid
:raises KeyError: This error is raised in the event there is something wrong with the rate limiting headers
:raises OktaAPIError: This error is raised any time the Okta API returns an error
"""

__docformat__ = 'restructuredtext'
import requests, json
from multiprocessing.context import AuthenticationError
from typing import List
import calendar, time

class OktaAPIError(Exception):
    """An error type for errors thrown by the Okta API. Takes in information about the request and formats error messages to make troubleshooting the errors easy."""
    
    def __init__(self, error_json_str: str, http_status: int, request_uri: str = None, request_method: str = None, request_body_str: str = None) -> None:
        """Initialize an OktaAPIError object and build the message property. 

        :param error_json_str: This is the error message returned in the error json from the Okta API
        :type error_json_str: str
        :param http_status: This is the http status code returned with the Okta API
        :type http_status: int
        :param request_uri: This is the URL of the Okta API call that generated the request, defaults to None
        :type request_uri: str, optional
        :param request_method: This is the http method of the failed request to the Okta API, defaults to None
        :type request_method: str, optional
        :param request_body_str: This is the request body of the failed request to the Okta API, defaults to None
        :type request_body_str: str, optional
        """
        self.message = 'Error JSON: %s | HTTP Status: %s' % (error_json_str, str(http_status))
        if request_uri is not None:
            self.message += ' | Request URI: %s' % request_uri
        if request_method is not None:
            self.message += ' | Request Method: %s' % request_method
        if request_body_str is not None:
            self.message += ' | Request Body: %s' % request_body_str
        super().__init__(self.message)

class OktaAPIBase:
    """Base class that can be used to perform common Okta API patterns in a multi-threaded way and a wrapper for Okta API calls that also handles rate limiting."""
    # this method needs to set the domain and api key
    def __init__(self, okta_domain: str, api_key: str) -> None:
        """Initialize the OktaAPIBase object with the proper Okta tenant and API key

        :param okta_domain: The domain of the Okta tenant (ex: acme.okta.com)
        :type okta_domain: str
        :param api_key: The Okta API key
        :type api_key: str
        """
        self.okta_domain = okta_domain
        self.api_key = api_key

    # wrap this method with your actual call methods
    def __oktaAPICall__(self, uri: str, method: str, rate_limit_buffer: int = None, **kwargs) -> requests.Response:
        """
        A method that is used to make all API calls, it handles setting up the http request as well as handles logic
        surrounding verifying the API key is valid and making sure the rate limit is not hit. This should be wrapped 
        by more specific (single input) functions for multi-threading purposes.

        :param uri: The request URI (ex: /api/v1/users)
        :type uri: str
        :param method: HTTP method for the request
        :type method: str
        :param rate_limit_buffer: How many calls below the rate limit will trigger a pause until the rate limit is reached, should be greater than the number of threads, defaults to None (when None it guesses based off which API endpoint)
        :type rate_limit_buffer: int, optional
        :raises AuthenticationError: This error will be thrown if the API key is invalid
        :raises KeyError: This error will be thrown if there are no rate limit headers
        :return: Response object from the request.request() call
        :rtype: requests.Response
        """
        headers = {
            'accept': "application/json",
            'content-type': "application/json",
            'authorization': "SSWS " + str(self.api_key),
        }
 
        # Strip the hostname and protocol prefix to enable the use of this function
        # with recursive Okta lookups
        uri = uri.replace(str('https://' + self.okta_domain), '').strip(' ')
        url = 'https://' + self.okta_domain + str(uri)
 
        # Accept kwargs, only 'payload' is currently supported with a PUT or POST method
        if 'payload' in kwargs.keys():
            payload = json.dumps(kwargs['payload'])
            response = requests.request(method,
                                    url,
                                    data=payload,
                                    headers=headers)
        else:
            response = requests.request(method, url, headers=headers)
 
        # check to see if API key is valid
        try:
            # DELETE Method returns no content, doing response.json() will throw an error
            # HTTP status code 204 = No Content
            if response.status_code != 204:
                if response.json()['errorCode'] == 'E0000011':
                    print('The API Key is invalid, please generate a new one and update the script')
                    raise AuthenticationError('Invalid API key')
        except(KeyError):
            pass
        except(TypeError):
            pass
 
        # if a specific rate limit buffer has not been given estimate what it should be based on the uri
        if rate_limit_buffer is None:
            rate_limit_buffer = self.estimate_rate_limit_buffer(uri)

        try:
            # make sure rate limit isnt being hit if this is called in a pool
            rateLimitValue = int(response.headers['x-rate-limit-remaining'])
            rateLimitReset = int(response.headers['x-rate-limit-reset'])
            if rateLimitValue < rate_limit_buffer:
                # print 'Waiting on rate limit'
                while int(calendar.timegm(time.gmtime())) < rateLimitReset + 5:
                    pass
        except KeyError as key_error:
            print(response.text)
            raise key_error
 
        return response

    def estimate_rate_limit_buffer(self, uri: str) -> int:
        """
        Takes the request URI as input and estimates what the rate limit buffer should be based on the total rate limit of the endpoint.
        Standard endpoint rate limits are found here: https://developer.okta.com/docs/reference/rl-global-mgmt/.
        For endpoints with rate limits <= 100 the buffer is 5, for the rest of the endpoints that have rate limits >= 500 the buffer is 20

        :param uri: Request URI for the Okta API call
        :type uri: str
        :return: Estimated buffer size for the endpoint in the request URI
        :rtype: int
        """
        # these numbers are the remaining amount of API calls before the API wrapper pauses until reset
        # these calls are the ones with rate limits around 100 or less
        if '/api/v1/apps' == uri or '/api/v1/logs' == uri or '/api/v1/events' == uri or '/oauth2/v1/clients' == uri or '/api/v1/certificateAuthorities' == uri or '/api/v1/devices' == uri:
            # limit is 100
            return 5
        # the rest of the endpoints have rate limits 500 or above
        else:
            return 20

    def get_single_resource(self, uri: str) -> dict:
        """
        GET the resource given by the URI. The URI should be exclusive to a single resource. This wrapps the __oktaAPICall__ method in a
        way that is multi-threadable. 

        :param uri: The URI of the single resource (ex: /api/v1/users/<user_id>). This should not have the possibility of returning more than one resource
        :type uri: str
        :raises OktaAPIError: Is raised when the Okta API returns an error for the given URI
        :return: The JSON object representation of the requested resource
        :rtype: dict
        """
        method = 'GET'
        response = self.__oktaAPICall__(uri, method)
        if response.status_code == 200:
            return response.json()
        else:
            raise OktaAPIError(str(response.json()), str(response.status_code), request_uri=uri, request_method=method)

    def get_multiple_resources(self, uri: str)  -> List[dict]:
        """
        Perform a GET on a URI that may return more than one resource. If there is pagination involved this method will
        iterate through all pages and return all resources in a list of JSON objects. 

        :param uri: The URI that is expected to return multiple resources (ex: /api/v1/users)
        :type uri: str
        :raises OktaAPIError: Is raised when the Okta API returns an error for the given URI
        :return: List of JSON objects that represent the requested resources
        :rtype: List[dict]
        """
        method = 'GET'
        response = self.__oktaAPICall__(uri, method)
        if response.status_code != 200:
            raise OktaAPIError(str(response.json()), str(response.status_code), request_uri=uri, request_method=method)
        
        resource_list = []
        resource_list += response.json()

        # pagination logic
        page = 1
        if len(response.headers['Link'].split(',')) > 1:
            print('Iterating through pages of users, each page contains 200 users, script will output the current page number every 10 pages')
        while len(response.headers['Link'].split(',')) > 1:
            page += 1
            if page % 10 == 0:
                print('Page %s' % page)
            uri = str(response.headers['Link'].split(',')[1].split(';')[0].strip(' ').strip('<').strip('>'))
            method = "GET"
 
            response = self.__oktaAPICall__(uri, method)
            if response.status_code != 200:
                raise OktaAPIError(str(response.json()), str(response.status_code), request_uri=uri, request_method=method)
            resource_list += response.json()
        
        return resource_list

    def delete_single_resource(self, uri: str)  -> None:
        """
        DELETE the Okta resource given by the URI. The URI should be exclusive to a single resource. This wrapps the __oktaAPICall__ method in a
        way that is multi-threadable. 

        :param uri: The URI of the single resource to be deleted (ex: /api/v1/users/<user_id>). This should not have the possibility of returning more than one resource
        :type uri: str
        :raises OktaAPIError: Is raised when the Okta API returns an error for the given URI
        :return: None if the resource was deleted successfully. This makes it easy to filter the result of this function being multi-threaded
        :rtype: None
        """
        method = 'DELETE'
        response = self.__oktaAPICall__(uri, method)
        if response.status_code == 204:
            return None
        else:
            raise OktaAPIError(str(response.json()), str(response.status_code), request_uri=uri, request_method=method)