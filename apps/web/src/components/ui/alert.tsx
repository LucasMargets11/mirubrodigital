import * as React from 'react';

const alertVariants = {
    default: 'bg-blue-50 border-blue-200 text-blue-900',
    destructive: 'bg-red-50 border-red-200 text-red-900',
};

interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
    variant?: keyof typeof alertVariants;
}

const Alert = React.forwardRef<HTMLDivElement, AlertProps>(
    ({ className = '', variant = 'default', children, ...props }, ref) => {
        return (
            <div
                ref={ref}
                role="alert"
                className={`relative w-full rounded-lg border p-4 [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg+div]:pl-7 ${alertVariants[variant]} ${className}`}
                {...props}
            >
                {children}
            </div>
        );
    }
);
Alert.displayName = 'Alert';

const AlertTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
    ({ className = '', ...props }, ref) => (
        <h5
            ref={ref}
            className={`mb-1 font-medium leading-none tracking-tight ${className}`}
            {...props}
        />
    )
);
AlertTitle.displayName = 'AlertTitle';

const AlertDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
    ({ className = '', ...props }, ref) => (
        <div
            ref={ref}
            className={`text-sm [&_p]:leading-relaxed ${className}`}
            {...props}
        />
    )
);
AlertDescription.displayName = 'AlertDescription';

export { Alert, AlertTitle, AlertDescription };
