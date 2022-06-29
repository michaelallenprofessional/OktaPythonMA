from okta_py_ma import OktaAPIBase, OktaAPIError

from multiprocessing import Pool

class OktaDeleter(OktaAPIBase):
    def __init__(self, okta_domain: str, api_key: str) -> None:
        super().__init__(okta_domain, api_key)
        self.deactivated_users = self.get_all_deactivated_users()
        
    def get_all_deactivated_users(self):
        return self.get_multiple_resources('/api/v1/users?filter=status+eq+"DEPROVISIONED"')

    def delete_user(self, user):
        try:
            # will return None on sucsessful delete
            return self.delete_single_resource('/api/v1/user/' + user['id'])
        except OktaAPIError as e:
            # return a string so a report can be created
            return str(e)

if __name__ == '__main__':
    p1 = Pool(10)
    okta_domain = ''
    api_key = ''
    okta_deleter = OktaDeleter(okta_domain, api_key)
    for user in okta_deleter.deactivated_users:
        print(user)

    # multi-thread delete users, filter out sucesses to return a list of error messages
    results = list(filter(list(p1.map(okta_deleter.delete_single_resource, okta_deleter.deactivated_users)), None))
    if len(results) == 0:
        print('All users sucessfully deleted')
    else:
        for error in results:
            print(error)