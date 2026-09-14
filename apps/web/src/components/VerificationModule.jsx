import React from 'react';
import CABQPVerification from './CABQPVerification.jsx';

/**
 * VerificationModule Component
 * 
 * Standard: Quality-first 2026 Production Architecture.
 * Serves as the primary operational module for the CA/BQP Verification Platform.
 * 
 * Features:
 * - Enterprise-grade Verification Pipeline (Intake -> OCR -> Policy Engine -> Resolution)
 * - Multi-tier classification (BCA, BQP, Dân sự, Cần thẩm định)
 * - Live interactive inspection modals: Original Dossier, Detailed Comparison Matrix, OCR Entity Inspector
 * - Real-time session history audit trail and state management
 */
export default function VerificationModule(props) {
  return <CABQPVerification {...props} />;
}
