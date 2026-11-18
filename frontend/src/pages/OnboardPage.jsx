import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

/** Legacy /onboard URL → back to dashboard (create org is a modal now). */
export default function OnboardPage() {
  const navigate = useNavigate();
  useEffect(() => {
    navigate("/", { replace: true });
  }, [navigate]);
  return null;
}
