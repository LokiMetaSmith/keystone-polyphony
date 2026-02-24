import nacl from 'tweetnacl';

export function toHex(byteArray) {
  return Array.from(byteArray, function(byte) {
    return ('0' + (byte & 0xFF).toString(16)).slice(-2);
  }).join('');
}

export function fromHex(hexString) {
  if (!hexString) return new Uint8Array();
  // Ensure even length for valid byte parsing
  if (hexString.length % 2 !== 0) {
      console.warn("Odd length hex string");
      return new Uint8Array();
  }
  const bytes = new Uint8Array(hexString.length / 2);
  for (let i = 0; i < hexString.length; i += 2) {
    bytes[i / 2] = parseInt(hexString.substr(i, 2), 16);
  }
  return bytes;
}

export function getIdentity() {
  const storedKey = localStorage.getItem('liminal_identity_key');
  if (storedKey) {
    try {
      const secretKey = fromHex(storedKey);
      if (secretKey.length === 64) {
          return nacl.sign.keyPair.fromSecretKey(secretKey);
      }
    } catch (e) {
      console.error("Invalid stored key", e);
    }
  }

  const keyPair = nacl.sign.keyPair();
  localStorage.setItem('liminal_identity_key', toHex(keyPair.secretKey));
  return keyPair;
}

export function signHex(hexString, keyPair) {
    const msgBytes = fromHex(hexString);
    const sig = nacl.sign.detached(msgBytes, keyPair.secretKey);
    return toHex(sig);
}

export function signString(str, keyPair) {
    const encoder = new TextEncoder();
    const msgBytes = encoder.encode(str);
    const sig = nacl.sign.detached(msgBytes, keyPair.secretKey);
    return toHex(sig);
}
