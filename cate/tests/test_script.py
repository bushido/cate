from __future__ import absolute_import, division, print_function, unicode_literals

import os
import unittest

from bitcoin.core import b2x, x, COIN, CMutableTransaction, CMutableTxIn, CMutableTxOut, COutPoint, Hash, Hash160
from bitcoin.core.script import SIGHASH_ALL, SignatureHash, CScript
from bitcoin.core.scripteval import MissingOpArgumentsError, VerifyOpFailedError, VerifyScript, SCRIPT_VERIFY_P2SH
from bitcoin.wallet import CBitcoinSecret, P2PKHBitcoinAddress
from cate.script import build_send_out_script

class TestSendScript(unittest.TestCase):
  def test_build_send_script(self):
    """ Run simple sanity checks on script generation """
    sender_public_key = x('02160dcd36ac266ea8dea3e483410ace007f5a648bac2df9b11b4f93641b421411')
    recipient_public_key = x('02f0383460e3d2609b3c69f4630bcc66abaf5f7419c06a6cc9a433eacf2258ff5b')
    secret_hash = x('f303d286d0047d2f3bad0e07a6a2350a783a30281229790925e3ef580c51de5e')
    script_elements = []
    for sig_element in build_send_out_script(sender_public_key, recipient_public_key, secret_hash):
      script_elements.append(sig_element)

    # Check the length of the script is as expected
    self.assertEqual(16, len(script_elements))

    # Verify each input is present
    self.assertEqual(Hash160(recipient_public_key), script_elements[2])
    self.assertEqual(Hash160(sender_public_key), script_elements[8])
    self.assertEqual(secret_hash, script_elements[13])

  def test_send_script_spend(self):
    """
    Run more in-depth execution checks on the script generated for the send transaction
    """
    sender_private_key = CBitcoinSecret.from_secret_bytes(x('4f65da9b656de4036076911707d2b2dbf065689245b8674faa8790e36d7e5850'))
    sender_public_key = sender_private_key.pub
    recipient_private_key = CBitcoinSecret.from_secret_bytes(x('cfe8e33672f7045f020210f3c7afbca660e053e4c9415c542ff185e97b175cf0'))
    recipient_public_key = recipient_private_key.pub
    secret = x('88d6e51f777b0b8dc0f429da9f372fbc')
    secret_hash = Hash(secret)
    send_to_key = CBitcoinSecret.from_secret_bytes(x('15a249b4c09286b877d4708191f1ee8de09903bae034dd9dc8e3286451fa1c80'))
    send_to_address = P2PKHBitcoinAddress.from_pubkey(send_to_key.pub)
    random_tx_id = x('8390b4c8198198c6447da1a6fad498209436a785459936b95a1e3b63618c1d8a')
    value = 10 * COIN

    send_tx_script_pub_key = build_send_out_script(sender_public_key, recipient_public_key, secret_hash)

    send_txins = [CMutableTxIn(COutPoint(random_tx_id, 0))]
    send_txouts = [CMutableTxOut(value, send_tx_script_pub_key)]
    send_tx = CMutableTransaction(send_txins, send_txouts)

    # Test the standard spend transaction

    txins = [CMutableTxIn(COutPoint(Hash(send_tx.serialize()), 0))]
    txouts = [CMutableTxOut(value, send_to_address.to_scriptPubKey())]
    recv_tx = CMutableTransaction(txins, txouts)

    sighash = SignatureHash(send_tx_script_pub_key, recv_tx, 0, SIGHASH_ALL)
    recipient_sig = recipient_private_key.sign(sighash) + (b'\x01') # bytes([SIGHASH_ALL])
    recv_tx.vin[0].scriptSig = CScript([secret, 0, recipient_sig, recipient_public_key])

    VerifyScript(recv_tx.vin[0].scriptSig, send_tx.vout[0].scriptPubKey, recv_tx, 0, (SCRIPT_VERIFY_P2SH,))

    # Test a refund transaction
    refund_tx = CMutableTransaction(txins, txouts)

    sighash = SignatureHash(send_tx_script_pub_key, refund_tx, 0, SIGHASH_ALL)
    sender_sig = sender_private_key.sign(sighash) + (b'\x01') # bytes([SIGHASH_ALL])
    recipient_sig = recipient_private_key.sign(sighash) + (b'\x01') # bytes([SIGHASH_ALL])
    refund_tx.vin[0].scriptSig = CScript([sender_sig, sender_public_key, 1, recipient_sig, recipient_public_key])

    VerifyScript(refund_tx.vin[0].scriptSig, send_tx_script_pub_key, refund_tx, 0, (SCRIPT_VERIFY_P2SH,))

    # Test invalid transactions are rejected

    invalid_tx = CMutableTransaction(txins, txouts)

    sighash = SignatureHash(send_tx_script_pub_key, invalid_tx, 0, SIGHASH_ALL)
    sender_sig = sender_private_key.sign(sighash) + (b'\x01') # bytes([SIGHASH_ALL])
    recipient_sig = recipient_private_key.sign(sighash) + (b'\x01') # bytes([SIGHASH_ALL])

    invalid_tx.vin[0].scriptSig = CScript([])
    with self.assertRaises(MissingOpArgumentsError):
      VerifyScript(invalid_tx.vin[0].scriptSig, send_tx_script_pub_key, invalid_tx, 0, (SCRIPT_VERIFY_P2SH,))

    invalid_tx.vin[0].scriptSig = CScript([recipient_sig, recipient_public_key, 0])
    with self.assertRaises(VerifyOpFailedError):
      VerifyScript(invalid_tx.vin[0].scriptSig, send_tx_script_pub_key, invalid_tx, 0, (SCRIPT_VERIFY_P2SH,))

    invalid_tx.vin[0].scriptSig = CScript([recipient_sig, recipient_public_key, 1])
    with self.assertRaises(VerifyOpFailedError):
      VerifyScript(invalid_tx.vin[0].scriptSig, send_tx_script_pub_key, invalid_tx, 0, (SCRIPT_VERIFY_P2SH,))

    invalid_tx.vin[0].scriptSig = CScript([recipient_sig, recipient_public_key, 1, recipient_sig, recipient_public_key])
    with self.assertRaises(VerifyOpFailedError):
      VerifyScript(invalid_tx.vin[0].scriptSig, send_tx_script_pub_key, invalid_tx, 0, (SCRIPT_VERIFY_P2SH,))

    invalid_tx.vin[0].scriptSig = CScript([sender_sig, sender_public_key, 1, sender_sig, sender_public_key])
    with self.assertRaises(VerifyOpFailedError):
      VerifyScript(invalid_tx.vin[0].scriptSig, send_tx_script_pub_key, invalid_tx, 0, (SCRIPT_VERIFY_P2SH,))
      
