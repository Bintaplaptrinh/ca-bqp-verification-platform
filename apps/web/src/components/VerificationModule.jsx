import React from 'react';
import CABQPVerification from './CABQPVerification.jsx';

/** Signed-in shell: renders the verification UI for the current user. */
export default function VerificationModule(props) {
  return <CABQPVerification {...props} />;
}
