use aes_gcm::aead::{Aead, AeadCore, KeyInit, OsRng};
use aes_gcm::{Aes256Gcm, Key, Nonce};
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use serde::{Deserialize, Serialize};
use thiserror::Error;

const KEY_LEN: usize = 32;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EncryptionEnvelope {
    pub envelope_version: u32,
    pub algorithm: String,
    pub key_id: String,
    pub nonce: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WorkspaceKey {
    bytes: [u8; KEY_LEN],
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EncryptedMarkdown {
    pub ciphertext: Vec<u8>,
    pub envelope: EncryptionEnvelope,
}

#[derive(Debug, Error)]
pub enum CryptoError {
    #[error("invalid workspace key")]
    InvalidKey,
    #[error("invalid nonce")]
    InvalidNonce,
    #[error("encryption failed")]
    Encrypt,
    #[error("decryption failed")]
    Decrypt,
}

impl WorkspaceKey {
    pub fn generate() -> Self {
        let key = Aes256Gcm::generate_key(&mut OsRng);
        Self { bytes: key.into() }
    }

    pub fn from_base64(value: &str) -> Result<Self, CryptoError> {
        let decoded = URL_SAFE_NO_PAD
            .decode(value.as_bytes())
            .map_err(|_| CryptoError::InvalidKey)?;
        let bytes: [u8; KEY_LEN] = decoded
            .try_into()
            .map_err(|_| CryptoError::InvalidKey)?;
        Ok(Self { bytes })
    }

    pub fn to_base64(&self) -> String {
        URL_SAFE_NO_PAD.encode(self.bytes)
    }

    pub fn encrypt_markdown(
        &self,
        key_id: &str,
        path: &str,
        plaintext: &[u8],
    ) -> Result<EncryptedMarkdown, CryptoError> {
        let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(&self.bytes));
        let nonce = Aes256Gcm::generate_nonce(&mut OsRng);
        let ciphertext = cipher
            .encrypt(
                &nonce,
                aes_gcm::aead::Payload {
                    msg: plaintext,
                    aad: path.as_bytes(),
                },
            )
            .map_err(|_| CryptoError::Encrypt)?;

        Ok(EncryptedMarkdown {
            ciphertext,
            envelope: EncryptionEnvelope {
                envelope_version: 1,
                algorithm: "AES-256-GCM".to_string(),
                key_id: key_id.to_string(),
                nonce: URL_SAFE_NO_PAD.encode(nonce),
            },
        })
    }

    pub fn decrypt_markdown(
        &self,
        path: &str,
        envelope: &EncryptionEnvelope,
        ciphertext: &[u8],
    ) -> Result<Vec<u8>, CryptoError> {
        if envelope.algorithm != "AES-256-GCM" || envelope.envelope_version != 1 {
            return Err(CryptoError::InvalidKey);
        }
        let nonce_bytes = URL_SAFE_NO_PAD
            .decode(envelope.nonce.as_bytes())
            .map_err(|_| CryptoError::InvalidNonce)?;
        let nonce = Nonce::from_slice(&nonce_bytes);
        let cipher = Aes256Gcm::new(Key::<Aes256Gcm>::from_slice(&self.bytes));
        cipher
            .decrypt(
                nonce,
                aes_gcm::aead::Payload {
                    msg: ciphertext,
                    aad: path.as_bytes(),
                },
            )
            .map_err(|_| CryptoError::Decrypt)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn encrypts_and_decrypts_markdown_with_path_aad() {
        let key = WorkspaceKey::generate();
        let path = "journal/2026/05/2026-05-23.md";
        let plaintext = b"# 2026-05-23\n\n## Decisions\n- Encrypt locally.\n";

        let encrypted = key
            .encrypt_markdown("workspace-key-v1", path, plaintext)
            .expect("encrypt");

        assert_ne!(encrypted.ciphertext, plaintext);
        assert_eq!(encrypted.envelope.algorithm, "AES-256-GCM");
        assert_eq!(
            key.decrypt_markdown(path, &encrypted.envelope, &encrypted.ciphertext)
                .expect("decrypt"),
            plaintext
        );
        assert!(key
            .decrypt_markdown(
                "journal/2026/05/2026-05-24.md",
                &encrypted.envelope,
                &encrypted.ciphertext,
            )
            .is_err());
    }

    #[test]
    fn workspace_key_roundtrips_as_base64() {
        let key = WorkspaceKey::generate();
        let encoded = key.to_base64();

        assert_eq!(WorkspaceKey::from_base64(&encoded).expect("decode"), key);
    }
}
