const SERVICE: &str = "ai-assistant-v2";

pub fn store_token(key: &str, value: &str) -> Result<(), keyring::Error> {
    keyring::Entry::new(SERVICE, key)?.set_password(value)
}

pub fn get_token(key: &str) -> Result<String, keyring::Error> {
    keyring::Entry::new(SERVICE, key)?.get_password()
}

pub fn delete_token(key: &str) -> Result<(), keyring::Error> {
    match keyring::Entry::new(SERVICE, key)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(error) => Err(error),
    }
}
