import requests, json
from multiprocessing.context import AuthenticationError
import calendar, time

class OktaAPIError(Exception):
    def __init__(self, error_json_str: str, http_status: int, request_uri: str = None, request_method: str = None, request_body_str: str = None) -> None:
        self.message = 'Error JSON: %s | HTTP Status: %s' % (error_json_str, str(http_status))
        if request_uri is not None:
            self.message += ' | Request URI: %s' % request_uri
        if request_method is not None:
            self.message += ' | Request Method: %s' % request_method
        if request_body_str is not None:
            self.message += ' | Request Body: %s' % request_body_str
        super().__init__(self.message)

class OktaAPIBase:
    # this method needs to set the domain and api key
    def __init__(self, okta_domain: str, api_key: str) -> None:
        self.okta_domain = okta_domain
        self.api_key = api_key

    # wrap this method with your actual call methods
    def __oktaAPICall__(self, uri: str, method: str, rate_limit_buffer: int = None, **kwargs) -> requests.Response:
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
        except KeyError as e:
            print(response.text)
            raise e
 
        return response

    def estimate_rate_limit_buffer(self, uri: str) -> int:
        # https://developer.okta.com/docs/reference/rl-global-mgmt/
        # these numbers are the remaining amount of API calls before the API wrapper pauses until reset
        # these calls are the ones with rate limits around 100 or less
        if '/api/v1/apps' == uri or '/api/v1/logs' == uri or '/api/v1/events' == uri or '/oauth2/v1/clients' == uri or '/api/v1/certificateAuthorities' == uri or '/api/v1/devices' == uri:
            # limit is 100
            return 5
        # the rest of the endpoints have rate limits 500 or above
        else:
            return 20

    def get_single_resource(self, uri: str) -> dict:
        method = 'GET'
        response = self.__oktaAPICall__(uri, method)
        if response.status_code == 200:
            return response.json()
        else:
            raise OktaAPIError(str(response.json()), str(response.status_code), request_uri=uri, request_method=method)

    def get_multiple_resources(self, uri: str)  -> dict:
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

    def delete_single_resource(self, uri: str)  -> dict:
        method = 'DELETE'
        response = self.__oktaAPICall__(uri, method)
        if response.status_code == 204:
            return None
        else:
            raise OktaAPIError(str(response.json()), str(response.status_code), request_uri=uri, request_method=method)