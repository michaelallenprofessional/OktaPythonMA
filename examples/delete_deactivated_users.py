from okta_py_ma import OktaAPIBase, OktaAPIError
from multiprocessing import Pool

class OktaDeleter(OktaAPIBase):
    """
    This class is a wrapper that performs the basic functionality of the script (aka 
    deleting all deactivated users in an org). The reason for wrapping a class like this
    is so if you need to perform the same functionality on multiple Okta orgs you can just
    loop the same code over multiple sets of okta_domain/api_key pairs.  
    """
    def __init__(self, okta_domain: str, api_key: str) -> None:
        """
        We overload the __init__ method by taking in the same inputs, but then automatically
        performing the first step in the logic (obtaining every deactivated user). 
        """
        super().__init__(okta_domain, api_key)
        self.deactivated_users = self.get_all_deactivated_users()
        
    def get_all_deactivated_users(self):
        """
        Wrapper that obtains all deactivated users in an org, verbose for clarity 
        """
        return self.get_multiple_resources('/api/v1/users?filter=status+eq+"DEPROVISIONED"')

    def delete_user(self, user: dict):
        """
        delete_user Deletes a user

        :param user: user dict format json object
        :type user: dict
        :return: None if user deleted, a str type message containing error information if the request failed
        :rtype: None if success, str if fail
        """
        try:
            # will return None on sucsessful delete
            return self.delete_single_resource('/api/v1/user/' + user['id'])
        except OktaAPIError as e:
            # return a string so a report can be created
            return str(e)

if __name__ == '__main__':
    p1 = Pool(10)
    # enter your Okta domain and API key here. Or, using best practices, source them from an environment variables.
    # BUT DO NOT COMMIT THEM TO A REPO
    okta_domain = ''
    api_key = '' 
    # set up object, the init will automatically get all deactivated users in the org
    okta_deleter = OktaDeleter(okta_domain, api_key)
    # print all users to be deleted for demo/logging purposes 
    for user in okta_deleter.deactivated_users:
        print(user)

    # multi-thread delete users, filter out sucesses to return a list of error messages
    results = list(filter(list(p1.map(okta_deleter.delete_single_resource, okta_deleter.deactivated_users)), None))
    # if the filter() function filtered out every element of the response list then all users were deleted properly
    if len(results) == 0:
        print('All users sucessfully deleted')
    # if there were remeaining elements in the list then there were errors, print them
    else:
        for error in results:
            print(error)